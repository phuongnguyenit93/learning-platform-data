# Ordering, Duplicates, Loss, and Delivery Guarantees

## Objectives

In a messaging system, simply sending a message is only the first step. The system must also determine whether the message is persisted durably, how many times it may be redelivered, what ordering is preserved, and what happens when the producer, broker, or consumer fails.

After this lesson, you will be able to:

- Distinguish send order, receive order, and processing completion order.
- Explain why a message can be delivered redundantly or lost.
- Distinguish at-most-once, at-least-once, and exactly-once.
- Understand the guarantee boundaries of abstractions in Spring Messaging.
- Design idempotent consumers and failure-recoverable processing flows.

## 1. What Does Spring Messaging Guarantee?

Spring Framework provides a general message model for components to exchange data:

- `Message<T>`: a message containing a payload and headers.
- `MessageHeaders`: metadata such as ID, timestamp, and application headers.
- `MessageChannel`: a point for sending messages.
- `MessageHandler`: a component that processes messages.
- `SubscribableChannel`: a channel allowing handlers to subscribe to receive messages.
- `PollableChannel`: a channel allowing consumers to actively pull messages.

Example of creating a message:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

record OrderCreated(String eventId, String orderId, long sequence) {}

OrderCreated event = new OrderCreated("evt-42", "order-17", 3);

Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader("eventId", event.eventId())
    .setHeader("aggregateId", event.orderId())
    .setHeader("sequence", event.sequence())
    .build();
~~~

The snippet above illustrates creating an envelope and attaching metadata; it assumes the `OrderCreated` type has already been declared. Headers can help consumers identify messages, group messages by business object, and check sequence order.

Key point: Spring Messaging defines message-exchange abstractions. `MessageChannel` by itself does not mandate that messages must be durably stored, delivered exactly once, retried, or kept in FIFO order. Those behaviors depend on the channel implementation, broker, adapter, and application configuration.

An in-memory channel within the same process has different characteristics from a queue or topic stored by a broker. When the process stops, messages residing in RAM-only data structures can disappear. When using Spring AMQP, Spring for Apache Kafka, JMS, or Spring Integration, check the delivery policies of the respective component; they cannot be inferred solely from the `Message<T>` type.

## 2. Three Concepts of Ordering

Three milestones must be distinguished:

1. **Send order:** which message the producer creates or sends first.
2. **Receive order:** which message the consumer sees first.
3. **Completion order:** which message's business logic finishes committing first.

These three orders can differ. For example, a producer sends event number 1 and then number 2. The consumer receives number 1 first, but processing number 1 takes longer so event number 2 finishes first. When consumers run concurrently, this happens very easily.

### 2.1. Why Can Ordering Change?

- Multiple producers send to the same destination concurrently.
- The broker distributes messages across multiple consumers.
- Consumers process asynchronously or use a thread pool.
- A failed message is retried while a subsequent message has already been processed.
- A message is sent to a dead-letter queue and replayed later.
- Priorities, routing, or multiple partitions create separate processing streams.

FIFO on a queue, if supported and properly configured by the broker, refers only to ordering within the scope defined by the broker. It does not automatically guarantee business completion order across multiple consumers or global system-wide ordering.

### 2.2. Preserving Order per Business Entity

Most systems do not need a global order across every message. The practical requirement is usually: all events for the same order, account, or record must be processed in order; different entities can still be processed in parallel.

A common approach:

- Attach a grouping key such as `aggregateId` to the message.
- Route messages sharing the same key to the same partition or sequential stream.
- Limit concurrency within each stream if completion order is mandatory.
- Attach a monotonically increasing business sequence number such as `sequence`.
- Have the consumer check the sequence number to detect late or missing messages.

For example, for order `order-17`, the consumer receives sequence 5 while sequence 4 has not yet been processed. The consumer can hold message 5 temporarily, retry, or request data reconciliation. Do not silently apply event 5 and skip 4 if business logic requires the complete history.

With Kafka, ordering is maintained within a single partition; messages with the same key are typically routed to the same partition according to the partitioning strategy. Ordering across partitions is not a global order. For other brokers, check FIFO scope and delivery semantics in the broker's documentation.

## 3. Why Are Messages Delivered Multiple Times?

Duplicate delivery is usually a normal consequence of recovery mechanisms, especially when a system uses retries or redelivery.

Typical scenarios:

1. The consumer executes the business action but crashes before sending an acknowledgement. The broker does not know processing completed, so it redelivers the message.
2. The producer sends a message but loses connection before receiving confirmation. The producer does not know whether the broker received it, so it resends.
3. The consumer times out while processing; the broker or adapter treats that attempt as failed and retries.
4. The application deliberately replays messages to recover data or rerun a processing flow.
5. One message is delivered to multiple subscribers under a pub/sub design. That is intentional fan-out delivery, not necessarily a duplicate.

Important example: a consumer successfully updates a balance in the database, then loses its connection before the acknowledgement reaches the broker. The broker redelivers the message. If the consumer adds the amount again, the balance becomes wrong even though the broker is following its redelivery policy properly.

### 3.1. Idempotency

An operation is **idempotent** when repeating it with the same input identifier does not alter the business outcome after the first execution.

Example:

- Unsafe: every time an `OrderPaid` event is received, add 100 to total revenue.
- Safer: record that the event with `eventId` has been applied; if that `eventId` appears again, skip the business side effect.

To achieve this:

- The producer generates a stable `eventId` when the business event is formed. All retries must reuse that ID.
- The consumer stores processed `eventId` values in a data store with a unique constraint.
- Recording `eventId` and updating business data must occur within the same database transaction whenever possible.
- If calling an external service, pass an idempotency key if that API supports it.

Do not rely by default on a framework- or broker-generated message ID as a long-term business identifier. Recreating a message or replaying data can produce a different transport ID. Carry a stable domain event ID instead.

### 3.2. The Inbox Pattern

An inbox is a table or store recording which messages the consumer has applied. A table can be designed with a unique key on `eventId`:

~~~sql
CREATE TABLE processed_messages (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Within a single transaction:

1. Attempt to insert `eventId` into the inbox table.
2. On unique-key violation, the message has already been processed; do not repeat the effect.
3. If the insert succeeds, update business data.
4. Commit both changes together.
5. Acknowledge the message only after the transaction succeeds.

If the application crashes before commit, both the inbox marker and the business update roll back. If commit succeeds but the acknowledgement is lost, the message may be redelivered; the unique key lets the consumer recognize the redelivery and avoid applying the business logic a second time.

## 4. Why Are Messages Lost?

Loss can happen at several stages: producer, network transit, broker, routing, consumer, or when writing business data.

| Point of Failure | Risk Example | Common Mitigation |
|---|---|---|
| Producer | Application crashes after committing business data but before sending the message | Transactional outbox |
| Sending to broker | Connection drops before learning whether the broker received it | Publisher confirms and retries with a stable `eventId` |
| Broker | Message lives only in memory or storage config is not durable enough | Durable destination, persistent messages, appropriate replication |
| Routing | No matching queue/subscriber or misconfigured binding | Verify routing, mandatory return, or broker equivalent |
| Consumer | Acknowledging before saving business results | Acknowledge after business transaction commits |
| Error handling | Retries expire and message is discarded | Dead-letter queue, alerts, and replay process |
| Message lifecycle | TTL expires or capacity limit evicts message | Choose appropriate TTL/retention and overflow policies |

An in-memory channel is suitable only when losing messages on process shutdown is acceptable or data can be regenerated. For critical business data, clearly define durable storage and recovery mechanisms.

### 4.1. Transactional Outbox

A dangerous gap exists if an application performs two separate operations:

1. Commit business changes to the database.
2. Send an event to the broker.

If the application crashes between the two steps, the database changed while the event was never sent. Reversing the order creates the opposite risk: the event is sent while the database transaction rolls back.

The transactional outbox closes this gap by writing business changes and an outbox record within the same database transaction. A relay process reads the outbox and publishes to the broker. After confirming successful delivery, the relay marks the record as published.

The relay can publish duplicates if it crashes after the broker accepts the message but before marking the outbox entry complete. Therefore, the outbox must be paired with a stable `eventId` and an idempotent consumer. The outbox ensures committed intent to emit events is not lost; it does not by itself make the entire system exactly-once.

## 5. Delivery Guarantee Levels

The following terms describe how many times a message may be delivered within a given scope and under specific failure assumptions.

| Guarantee Level | Meaning | Trade-Off |
|---|---|---|
| **At-most-once** | Message is delivered at most one time; may not be delivered at all | Avoids duplicate delivery, but messages can be lost |
| **At-least-once** | System keeps redelivering until confirmation conditions or stop policy are met | Reduces risk of message loss, but consumers must tolerate duplicates |
| **Exactly-once** | One message has exactly one effect within the scope protected by a transactional mechanism | Scope is usually limited; hard to extend across multiple systems |
| **Effectively-once** | Message may be delivered multiple times, but business effects are deduplicated | Requires stable IDs, idempotency, and proper state persistence |

### 5.1. At-Most-Once

The system does not retry, or acknowledges the message before processing. If the consumer crashes after the broker removes the message but before business logic completes, the message is lost.

This level can fit ephemeral data, status updates recoverable from another source, or telemetry where losing some data is acceptable.

### 5.2. At-Least-Once

The consumer acknowledges only after successful processing. If the consumer crashes before acknowledgement, the broker redelivers the message. This prioritizes not dropping messages, though duplicates must be anticipated.

This is the common choice for critical business operations when consumers are designed to be idempotent. Bounded retries or backoff policies, a dead-letter queue, and alerts are needed so failing messages do not loop indefinitely.

### 5.3. Exactly-Once and Practical Limits

Exactly-once must be understood within a specific boundary. A broker or streaming platform can support transactions to ensure a sequence of reading, processing, and writing to destinations managed by the same transactional mechanism. That does not automatically guarantee an email is sent only once, an HTTP call happens only once, or a database update outside the broker's transaction happens only once.

If a consumer updates a database and then calls a payment API, the two systems typically do not share a distributed transaction. When a failure occurs between the two operations, the application needs idempotency keys, outbox/inbox, controlled retries, or compensation workflows. Hence, in application design, the practical goal is usually **effectively-once business effects** achieved via idempotent processing and proper transactions.

## 6. Acknowledgements and Retries

An acknowledgement (ack) is a signal sent by a consumer to tell the broker that a message has reached a certain processing state. Distinguish between:

- **Publisher confirm:** confirmation from the broker regarding publish acceptance according to broker semantics.
- **Consumer acknowledgement:** the consumer confirms the message has been processed or accepted according to delivery policy.

The two mechanisms sit at opposite ends. A publisher confirm does not prove the consumer processed the message. A consumer ack does not prove all external side effects completed if the application acks too early.

A safe processing sequence typically looks like:

~~~text
Producer
  -> write business data and outbox in one database transaction
  -> relay publishes message
  -> receive publisher confirm
  -> Broker persists message per durability configuration
  -> Consumer receives message
  -> check inbox/eventId
  -> update business data and inbox in one transaction
  -> commit
  -> Consumer acknowledgement
~~~

If the consumer fails before commit, the transaction rolls back and the message can be redelivered. If the consumer commits but the ack is lost, the message can be redelivered; the inbox prevents duplicate side effects.

Retries should be bounded with increasing wait intervals (backoff). Classify errors:

- Transient errors such as timeouts or unavailable dependencies: can be retried.
- Invalid data or incompatible schema errors: retries usually cannot fix them; route to dead-letter for investigation.
- Business errors may require waiting for conditions or manual intervention; define an explicit policy.

A dead-letter queue does not fix messages automatically. Monitor it, identify root causes, fix data or code, and replay in a controlled manner. When replaying, preserve the original `eventId` so idempotency continues to work.

## 7. Applying the Principles in Spring

Spring Messaging provides common contracts for sending and handling messages. Example of a handler:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.MessagingException;

public final class OrderCreatedHandler implements MessageHandler {
    @Override
    public void handleMessage(Message<?> message) throws MessagingException {
        Object eventId = message.getHeaders().get("eventId");
        Object aggregateId = message.getHeaders().get("aggregateId");

        // Validate metadata, then invoke the idempotent business service.
        // Transaction and acknowledgement policies depend on the adapter/broker.
    }
}
~~~

This is a handler implementation, not a standalone runnable application. With a channel, sending may look like:

~~~java
boolean accepted = messageChannel.send(message);
~~~

The return value must be interpreted solely according to the contract of the channel in use. It is not general proof that the broker durably persisted the message or that the consumer finished processing.

When integrating a broker:

- Configure publisher confirms/returns according to broker and adapter capabilities.
- Choose persistent messages, durable queues/topics, replication, and retention per recovery requirements.
- Choose an appropriate acknowledgement mode and ack timing.
- Configure retries, backoff, dead-lettering, and redelivery limits.
- Place `eventId`, `aggregateId`, and `sequence` in headers or payload per the application's data contract.
- Measure publish failures, redeliveries, retries, latency, message age, and dead-letter counts.

Configuration details differ across Spring AMQP, Spring for Apache Kafka, JMS, and Spring Integration. Do not copy an ack or retry setting from one broker to another without checking the adapter's semantics.

## 8. Java 17 Example: Consumer Ignoring Already-Seen Events

The standalone example below simulates receiving the same event twice. It uses an in-memory `Set` to illustrate the idempotency principle; it is not durable state storage for production.

File: `IdempotentConsumerDemo.java`

~~~java
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

record Event(String id, String type) {}

public class IdempotentConsumerDemo {
    private final Set<String> processedIds = ConcurrentHashMap.newKeySet();

    public void onMessage(Event event) {
        if (!processedIds.add(event.id())) {
            System.out.println("duplicate ignored: " + event.id());
            return;
        }

        applyBusinessEffect(event);
    }

    private void applyBusinessEffect(Event event) {
        System.out.println("processed: " + event.id() + " -> " + event.type());
    }

    public static void main(String[] args) {
        IdempotentConsumerDemo consumer = new IdempotentConsumerDemo();
        Event event = new Event("evt-42", "OrderCreated");

        consumer.onMessage(event);
        consumer.onMessage(event);
    }
}
~~~

Compile and run with Java 17 or higher:

~~~bash
javac IdempotentConsumerDemo.java
java IdempotentConsumerDemo
~~~

Stdout output:

~~~text
processed: evt-42 -> OrderCreated
duplicate ignored: evt-42
~~~

The first time, the `Set` accepts `eventId`, so the consumer executes the side effect. The second time, `eventId` is already present, so the consumer skips it.

In a real application, an in-memory `Set` loses its data on process restart and is not shared across multiple instances. There is also a failure window if the application adds the ID to the `Set` and crashes before performing the business action. Use a durable inbox or deduplication table with a unique constraint, and record the processed marker in the same transaction as the business update.

## 9. Combining Guarantees According to Requirements

| Business Requirement | Typically Suitable Design |
|---|---|
| Partial data loss acceptable, low latency prioritized | At-most-once, regenerable data source |
| Must not drop committed events | Outbox, durable broker, publisher confirms |
| Consumer may receive duplicate messages | At-least-once combined with inbox/idempotency |
| Preserve order of changes per order | Partitioning/routing by `orderId` and sequence |
| Recover failed messages | Bounded retries, dead-letter queue, and replay |
| Side effects across multiple services | Stable `eventId`, idempotency keys, outbox/inbox, and compensation workflows |

There is no single configuration optimal for every system. Clarify what matters most: zero data loss, avoiding duplicate processing, preserving order, throughput, or latency. A system can preserve order per aggregate while processing concurrently across aggregates; it can use at-least-once at the transport layer and effectively-once at the business layer.

## 10. Common Design Mistakes

- Assuming `MessageChannel.send()` succeeding means the broker durably persisted the message.
- Using auto-ack or acking before the business transaction commits while expecting no data loss.
- Retrying a message while generating a new `eventId` on every send, preventing the consumer from detecting duplicates.
- Using identical payloads to infer two messages represent the same event; two valid events can have identical payloads.
- Running a concurrent consumer while assuming completion order always matches receive order.
- Assuming FIFO on one queue guarantees global ordering across multiple queues, partitions, or consumers.
- Routing failed messages to a dead-letter queue and forgetting monitoring and replay procedures.
- Writing to the inbox and updating business data in two separate transactions, creating a new failure window.
- Calling a flow exactly-once without specifying the transaction boundary and systems outside that boundary.

## 11. Design Checklist

- [ ] Every business event has a stable `eventId` across all retries and replays.
- [ ] Ordering scope is defined: global, per partition, or per aggregate.
- [ ] Sequence numbers are present if out-of-order or missing events must be detected.
- [ ] At-most-once or at-least-once is chosen based on tolerance for data loss.
- [ ] Consumers are idempotent; inbox markers and business effects commit together whenever possible.
- [ ] Producers use an outbox if event emission must align with a business transaction.
- [ ] Durability, publisher confirms, and consumer acknowledgements are configured per broker.
- [ ] Retries are bounded with backoff and a dead-letter queue.
- [ ] Alerts and an investigation/replay procedure exist for dead letters.
- [ ] `eventId`, `correlationId`, `aggregateId`, `sequence`, retry counts, and processing latency are tracked.
- [ ] Crash before commit, crash after commit before ack, and connection loss during publish have been tested.

## 12. References

- [Spring Framework — Message](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/Message.html)
- [Spring Framework — MessageChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html)
- [Spring Framework — MessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHandler.html)
- [Spring Framework — MessageBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html)
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html)
- [Spring for Apache Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring AMQP Reference](https://docs.spring.io/spring-amqp/reference/)
