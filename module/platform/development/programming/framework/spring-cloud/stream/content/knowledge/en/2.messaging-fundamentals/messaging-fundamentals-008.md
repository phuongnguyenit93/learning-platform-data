# Duplicate, Late, and Out-of-Order Messages

In an event-processing system, producers send messages to a broker and consumers process them when possible. Between emission and processing, network errors, process restarts, retries, backlogs, or changes in consumer count can occur. As a result, a message can be delivered multiple times, arrive after a newer message, or be processed after an event that occurred later in business time.

These are normal scenarios that must be anticipated in messaging design. A Spring Cloud Stream application can use the same `Supplier`/`Function`/`Consumer` model with Kafka, RabbitMQ, or Pulsar, yet each broker and binder has its own delivery, routing, acknowledgement, and ordering semantics. Business logic must determine which messages have already been applied, which messages are missing predecessors, and how late data should be handled.

This lesson belongs to the **Messaging Fundamentals** chapter of the `SPRING_CLOUD_STREAM` module. The goal is to distinguish the three phenomena, understand their causes, and build consumers resilient to duplicates, latency, and out-of-order arrival.

## 1. Distinguishing the Three Phenomena

These three concepts are often lumped together, yet they describe different problems:

| Phenomenon | Meaning | Example |
|---|---|---|
| Duplicate message | The same event is delivered or processed more than once | The consumer updated an order, then crashed before the broker received an ack; the broker redelivers the message |
| Late message | A message is processed late relative to when the event occurred or the expected business deadline | A payment event occurred at 10:00 but is only processed by the consumer at 10:08 due to backlog |
| Out-of-order message | Sequentially related events are processed in an order different from business order | The consumer receives `OrderShipped` before `OrderPaid` even though payment happened before shipping |

A message can be both late and out of order. A duplicate message can also arrive after a newer message. Consequently, a single measure such as increasing retry counts cannot solve all three problems.

For example, order `ORD-42` emits three events:

```text
Business order:
v1 OrderPlaced  ------> v2 PaymentAuthorized ------> v3 OrderShipped

Order observed by consumer:
v1 OrderPlaced  ------> v3 OrderShipped ----------> v2 PaymentAuthorized
                         ^
                         |
                   v1 may be redelivered
```

The consumer needs to know that `v1`, `v2`, and `v3` belong to the same order and carry version numbers. Relying solely on message arrival time is not enough to determine which event belongs first.

## 2. Why Can a Message Be Delivered Multiple Times?

In at-least-once delivery, the broker or framework keeps attempting delivery until it receives an acknowledgement under its mechanism. This reduces message loss risk, but it can produce redeliveries. Common causes include:

- The consumer completed business work but crashed before acknowledging the message. When the consumer restarts or partition/queue ownership transfers, the message can be redelivered.
- The acknowledgement was lost in transit. The broker does not know the consumer succeeded and continues delivering the message.
- A producer retried after a timeout without receiving broker confirmation, even though the earlier send was actually persisted.
- Retry settings, redeliveries, or replaying from a dead-letter queue (DLQ) reintroduce the same event into the processing stream.
- A transactional outbox relay re-emits a record not yet marked published, even though an earlier send may have reached the broker.

Consider a consumer that updates stock by subtracting 1:

1. The consumer receives `InventoryReserved`.
2. The database decrements stock from 20 to 19.
3. The process stops before the broker receives the acknowledgement.
4. The broker redelivers the same message.
5. The consumer decrements stock again, leaving 18.

The broker behaved according to its delivery guarantee. The bug lies in business logic failing to recognize an already-applied event. Consumers must be idempotent: processing the same event again does not alter the business outcome a second time.

## 3. At-Most-Once, At-Least-Once, and Exactly-Once

These terms describe how many times a message or processing effect can occur within a given guarantee scope:

| Mechanism | Characteristics | Trade-off |
|---|---|---|
| At-most-once | Delivered or processed at most once within the configured scope | Messages can be lost if acknowledged before processing completes and a crash occurs |
| At-least-once | Delivery is retried until acknowledgement criteria are met | Duplicates are possible; consumers must handle duplicates safely |
| Exactly-once | Effects are guaranteed strictly once within a supported system scope | Scope is typically bounded by broker, transactions, and integration design; does not automatically cover external systems |

Do not interpret exactly-once as a message crossing the network strictly once. A system may deliver a message multiple times while using transactions or deduplication to ensure the final effect is recorded only once within a defined boundary. If a consumer updates a database and calls an external payment API, broker transactions generally do not span both operations automatically.

Therefore, practical designs usually pair at-least-once with idempotent consumers. This lets systems recover from failures without turning a redelivery into a new business execution.

## 4. Identifying Events with Stable Identifiers

Each business event should have a stable `eventId`, generated when the event is created and preserved across all retries and replays. An event also typically needs an entity identifier, version, and occurrence timestamp:

```json
{
  "eventId": "7f4bcb2a-4f75-4d6b-ae61-1b3a6c2b1a70",
  "eventType": "PaymentAuthorized",
  "schemaVersion": 1,
  "aggregateId": "ORD-42",
  "aggregateVersion": 2,
  "occurredAt": "2026-11-24T03:00:00Z",
  "correlationId": "checkout-9d81",
  "amount": 1250000,
  "currency": "VND"
}
```

Each field plays a distinct role:

- `eventId` identifies a single event emission. Consumers use it to detect redeliveries of the same event.
- `aggregateId` identifies the entity described by the event stream, such as an order ID.
- `aggregateVersion` or `sequenceNumber` expresses event order within an entity. It helps detect stale events, duplicates, and sequence gaps.
- `occurredAt` records when the business event occurred, usually normalized to UTC. This is not necessarily when the broker received the message.
- `schemaVersion` indicates payload structure version so consumers can apply compatible rules.
- `correlationId` links messages belonging to the same processing flow, aiding cross-service tracing.

Do not use timestamps as unique identifiers. Two events can share the same timestamp, machine clocks can drift, and timestamp resolution is insufficient to represent total ordering. `eventId` and per-aggregate sequence numbers solve two separate needs.

## 5. Building an Idempotent Consumer

A common approach uses an **inbox table** storing processed event IDs. This table has a unique constraint on `event_id`. Within the same database transaction, the consumer checks or records the event ID and updates business data. If the message is redelivered, the consumer sees it is already in the inbox and skips repeating the effect.

Example schema:

```sql
CREATE TABLE processed_message (
    event_id       VARCHAR(80) PRIMARY KEY,
    aggregate_id   VARCHAR(80) NOT NULL,
    processed_at   TIMESTAMP NOT NULL
);
```

Business handling can be structured as follows. The repositories are application abstractions; `findByIdForUpdate` should lock the aggregate row in the transaction or use an equivalent concurrency-control mechanism.

```java
import java.time.Instant;
import java.util.UUID;

import org.springframework.transaction.annotation.Transactional;
import org.springframework.stereotype.Service;

record OrderEvent(
    UUID eventId,
    String orderId,
    long version,
    String eventType,
    Instant occurredAt
) {}

@Service
class OrderEventHandler {

    private final ProcessedMessageRepository processedMessages;
    private final OrderRepository orders;

    OrderEventHandler(
            ProcessedMessageRepository processedMessages,
            OrderRepository orders) {
        this.processedMessages = processedMessages;
        this.orders = orders;
    }

    @Transactional
    public void handle(OrderEvent event) {
        if (processedMessages.existsById(event.eventId())) {
            return;
        }

        Order order = orders.findByIdForUpdate(event.orderId())
            .orElseThrow();

        if (event.version() <= order.getVersion()) {
            // Stale event or already reflected in the current state.
            processedMessages.save(event.eventId(), event.orderId());
            return;
        }

        if (event.version() != order.getVersion() + 1) {
            throw new MissingPredecessorException(
                "Missing event before version " + event.version());
        }

        order.apply(event);
        processedMessages.save(event.eventId(), event.orderId());
    }
}
```

This example illustrates the principle rather than a standalone runnable repository layer. In real deployments:

- Recording the inbox entry and updating the aggregate must share the same database transaction. If the business update commits while the inbox write does not, redelivery can still cause duplicate effects.
- `event_id` must be unique in the database. Checking `existsById` alone risks race conditions when two threads process the same event concurrently; a unique constraint and conflict handling provide the final safeguard.
- Locking or optimistic locking must protect updates to the same aggregate when multiple messages run concurrently.
- Define a retention period for inbox records. Deleting markers too early allows a historical replay to re-execute business logic.

If the consumer calls external services such as payment gateways or email providers, database transactions cannot automatically roll back external effects. Pass a stable idempotency key if the target API supports one, or write outbound requests to an outbox so another process executes and tracks outcomes. For operations that cannot be safely repeated, establish reconciliation and manual resolution workflows when status is ambiguous.

## 6. Detecting Stale, Current, and Missing Messages

`aggregateVersion` lets consumers compare an incoming event against stored state:

| Condition | Interpretation | Common Handling |
|---|---|---|
| `event.version` less than or equal to current version | Stale, duplicate, or already-reflected event | Check event ID; if state already reflects that version, skip duplicate effects and mark as processed |
| `event.version` equal to current version plus one | Next event in sequence | Apply the event and increment version within the same transaction |
| `event.version` greater than current version plus one | Gap detected; predecessor event missing | Wait with bounds, buffer temporarily, request replay, or resync state; do not silently ignore gaps |

For example, the consumer is at version 4 and receives version 6. Applying version 6 immediately could skip the transition in version 5. If business rules require every transition to run, the consumer must wait for or recover the missing event. If the message is a full snapshot where newer versions completely replace older state, different rules may apply; the event contract must state that explicitly.

Throwing an exception for infinite retries is not always right. If version 6 blocks a partition while version 5 sits behind it in the same partition, retrying in place could prevent version 5 from ever being processed. Depending on the broker and business flow, you can park version 6 in a pending table, move it to a bounded-delay retry stream, or ask the producer to replay from the source of truth. When version 5 arrives, the consumer processes queued versions in order.

## 7. Late Messages and Event Time

A message has at least three timestamps to distinguish:

- **Event time:** when the event actually occurred in the business domain, usually recorded by the producer in `occurredAt`.
- **Ingestion time:** when the broker or streaming system received the message.
- **Processing time:** when the consumer actually started or finished processing the message.

For example, a sensor records temperature at 10:00, loses connectivity, and sends the data at 10:12. Event time is 10:00, ingestion time is 10:12, and processing time may be 10:12:03. If reports group only by processing time, data appears in the 10:12 bucket even though it describes what happened at 10:00.

Late messages can result from offline producers, broker backlogs, under-provisioned consumers, prolonged retries, DLQ replays, or network partitions. In windowed analytics systems, an event with an older event time may arrive after its window has already been computed.

With event-time processing, streaming systems often use watermarks to estimate data completeness by event time. Windows may allow a grace period to accept late data. After that deadline, the system can drop the event, update published results, or emit a correction depending on business rules. A watermark is a progress estimate, not proof that an older message will never arrive.

In online transactional flows, late-data policies can differ from analytics. For example, a `PaymentAuthorized` event arriving late after an order was already canceled must follow compensation or refund rules rather than simply being dropped because its timestamp is old. Occurrence time explains history; current state and state-transition rules dictate valid actions.

## 8. Why Can Message Order Change?

Brokers usually guarantee ordering only within a specific scope. Global ordering across an entire topic, queue, or subscription may not exist when systems partition data, run multiple consumers, or retry failed messages.

Common causes include:

1. Producers send multiple messages concurrently, causing send order and broker write order to differ.
2. Messages are split across different partitions or queues; each stream has its own order.
3. Multiple consumers process concurrently, so an earlier message may finish after a later message.
4. Failed messages are retried or requeued while newer messages continue processing.
5. Consumer group rebalances or instance scaling transfer processing ownership to other consumers.
6. Producers or consumers asynchronously decouple sending, receiving, and database writes without preserving per-aggregate order.

### Ordering by Broker

| Broker | Ordering Scope to Note | Design Implication |
|---|---|---|
| Kafka | Order is guaranteed within one partition; no total order across partitions | Use a stable key such as `orderId` so events for one order enter the same partition; process concurrently across partitions |
| RabbitMQ | A single queue has basic delivery order, but multiple consumers, prefetch, redeliveries, priorities, and requeues can alter completion order | If strict order is needed, limit concurrent consumers on that stream or partition by aggregate and serialize updates |
| Pulsar | Order depends on subscription type, partitions, and keys; load-sharing subscriptions may process concurrently | Pick the right subscription type; use ordering keys or `Key_Shared` with compatible producer settings when key order is needed |

Even when the broker delivers messages in order, an application can still break ordering by handing received messages to an async thread pool without per-key coordination. Ordering guarantees must hold end to end across producer, broker, binder, consumer, and database.

### Consumer Groups and Concurrency

Consumer groups let multiple instances share the load of an input stream. In Kafka, within one consumer group, each partition is assigned to one consumer at a time; partition count bounds the group's consumption parallelism. Different groups can read the same topic independently. RabbitMQ and Pulsar have their own load-sharing/subscription models, even though Spring Cloud Stream provides a similar `group` abstraction.

Raising concurrency can boost throughput, but it does not automatically preserve business order. If events for the same aggregate run on multiple threads without locking or version checks, updates can overwrite one another. Choose concurrency along units that can execute independently, typically across distinct aggregates.

## 9. Preserving Order per Aggregate

When ordering matters, define clearly **the unit that must stay ordered**. In an ordering system, events for one order need ordering; two different orders can run in parallel. Therefore:

1. Attach `aggregateId` and `aggregateVersion` to every event.
2. Use `aggregateId` as the partition key, routing key, or ordering key as supported by the broker.
3. Configure consumers so messages with the same key are not processed concurrently in ways that invert order.
4. Use version checks or optimistic locking at the database to detect out-of-order updates.
5. Define how to handle missing versions and how to recover after retries or replays.

With Kafka, producers can route messages with the same key to the same partition. However, increasing or changing partition counts can change key-to-partition mapping depending on the partitioner; plan ahead when scaling topics if historical per-key ordering is strict. With RabbitMQ, routing keys only control exchange routing; keeping one aggregate on a sequential stream requires appropriate topology and consumer setup. With Pulsar, ordering keys and subscription types must be chosen together.

Example Spring Cloud Stream input binding configuration:

```yaml
spring:
  cloud:
    function:
      definition: orderEvents
    stream:
      bindings:
        orderEvents-in-0:
          destination: orders.events
          group: inventory-projection
          consumer:
            concurrency: 3
```

`group` identifies the consumer group in Spring Cloud Stream's abstraction. `concurrency` instructs the binder to create parallelism within its capabilities. This configuration snippet does not create ordering by `orderId`, nor does it protect an aggregate from concurrent processing. Producer partitioning, key expressions, routing or ordering keys, and specific delivery options are configured per binder in use.

## 10. Spring Cloud Stream Consumer Example

A `Consumer` function can accept `Message<OrderEvent>` to read payload and headers. Business logic is delegated to a separate service so database transactions have clear boundaries:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
class OrderEventConsumerConfiguration {

    @Bean
    Consumer<Message<OrderEvent>> orderEvents(OrderEventHandler handler) {
        return message -> {
            OrderEvent event = message.getPayload();
            handler.handle(event);
        };
    }
}
```

The function's default binding is `orderEvents-in-0`, which can be connected to a destination and group in configuration. Once the binder determines whether processing succeeded or failed, it applies acknowledgement, retry, or error routing per configuration and broker capabilities. Exact acknowledgement and DLQ details differ across Kafka, Rabbit, and Pulsar binders; do not copy one binder's error configuration directly to another.

Guidelines when implementing consumers:

- Let the function return successfully after business work commits. If a message is acknowledged before data is saved, a crash can lose the required effect.
- For transient failures, use bounded retries with backoff; avoid aggressive retries that amplify load.
- If a message cannot be processed due to invalid data or schema incompatibility, route it to a DLQ or quarantine stream per policy for investigation.
- When replaying from a DLQ, preserve `eventId`, `aggregateId`, version, and event time. A replay is a redelivery of an old event, not a new business event.
- Avoid doing long work on the message-receiving thread if it stalls a partition or consumer too long. If offloading to async processing, enforce bounds and per-key ordering where needed.

## 11. Retries, DLQs, and Reordering Risks

Retries address recoverable errors such as brief timeouts or temporarily unavailable dependencies. DLQs isolate messages that fail after the retry policy. Both mechanisms directly impact ordering:

- In-place retries can pause the stream on the failing message. This avoids skipping ahead in some setups, but it can block other messages in the same partition or queue.
- Requeuing or retrying via another topic/queue can let newer messages overtake the failing message.
- A DLQ pulls a message out of the main stream. When fixed and replayed later, it may arrive after many newer versions.

Classify errors accordingly. Transient failures can retry with bounded attempts and wait times. Data errors or contract violations generally require a DLQ and intervention. Missing-predecessor errors require waiting or state resynchronization rather than being treated like ordinary infrastructure errors.

Before replaying, verify whether consumers can process older events without regressing state. Use version checks, inbox records, and per-aggregate replay workflows. If a message is skipped because state has already moved ahead, log the reason for auditability.

## 12. Testing Abnormal Scenarios

A test that only sends one happy-path message does not prove consumer safety. Create targeted scenarios:

| Scenario | How to Simulate | What to Verify |
|---|---|---|
| Same message delivered twice | Send two copies with the same `eventId` | Business data mutates only once |
| Crash after commit before ack | Stop the consumer at the right boundary and let the broker redeliver | Consumer detects redelivery and does not repeat side effects |
| Stale message arrives late | Send version 3 after state is already at version 4 | State does not regress; event is recorded or handled per policy |
| Missing version | Send version 6 when consumer is at version 4 | Consumer detects the gap and follows waiting/recovery rules |
| Late after window closes | Send an old event time past configured watermark or grace period | Result is dropped, amended, or quarantined per policy |
| Retry and DLQ | Fail the handler repeatedly, then replay the message | Retry count, DLQ contents, and replay behave as controlled |
| Concurrent load | Send multiple aggregates and multiple events per aggregate | Independent aggregates run in parallel; required per-aggregate order holds |

Integration tests should use a real broker or sufficiently faithful environment to verify binder behavior, since mocking consumer functions cannot test partitions, acknowledgements, redeliveries, or subscription semantics. Tests should also verify that configuration matches the application's actual binder and dependency versions.

## 13. Observability and Operations

These metrics help detect issues before they become data discrepancies:

- Processed message counts, redelivery counts, and event IDs skipped due to prior processing.
- Consumer lag or backlog, age of oldest message, and latency from `occurredAt` to processing time.
- Retry counts, error rates, DLQ message counts, and replay counts.
- Out-of-order event counts, version gap counts, and wait time to recover an aggregate.
- Processing duration, transaction rollback rates, and optimistic locking conflicts.

Logs should include `eventId`, `aggregateId`, `aggregateVersion`, and `correlationId` when available. Do not log full sensitive payloads. During investigations, distinguish a redelivered message from a brand-new business event with similar content.

## 14. Recommended Processing Workflow

When designing a Spring Cloud Stream consumer, follow this sequence:

1. Clarify whether messages represent events or commands and assign a stable `eventId`.
2. Identify the aggregate, version/sequence, and scope requiring ordering.
3. Choose the broker, binder, group, partitioning, or subscription matching load and ordering needs.
4. Make the consumer idempotent via an inbox, unique constraint, or equivalent tracking mechanism.
5. Place business updates and processed-event markers inside the same database transaction when both reside in that database.
6. Define policies for stale messages, missing predecessors, and event-time late arrivals.
7. Configure bounded retries, backoff, DLQs, and replay procedures.
8. Test duplicates, crashes at ack boundaries, parallel load, out-of-order delivery, and data recovery.
9. Monitor lag, latency, duplicates, version gaps, retries, and DLQs in deployed environments.

## 15. Self-Check

- [ ] Can distinguish duplicate, late, and out-of-order messages.
- [ ] Can explain why at-least-once can redeliver messages and why consumers must be idempotent.
- [ ] Knows the roles of `eventId`, `aggregateId`, `aggregateVersion`, `occurredAt`, and `correlationId`.
- [ ] Can describe how an inbox table and database transaction prevent duplicate effects.
- [ ] Can distinguish event time, ingestion time, and processing time.
- [ ] Knows within what scope ordering is guaranteed in Kafka, RabbitMQ, and Pulsar.
- [ ] Understands that consumer groups and concurrency share load but do not automatically guarantee business order.
- [ ] Has policies for retry, DLQ, replay, and observability for failed or late messages.

## Conclusion

Duplicate, late, and out-of-order messages are realities to plan for in asynchronous systems. `eventId` identifies an event occurrence, inboxes and transactions prevent duplicate side effects, and aggregate versions plus routing keys detect or reduce reordering. Event time supports late-data handling, while retries, DLQs, and replays require clear policies so business state stays consistent. Spring Cloud Stream provides a unified abstraction for applications, but final guarantees still depend on the binder, broker, and how consumers design transactions and state.
