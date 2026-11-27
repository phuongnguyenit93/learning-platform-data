# Durable Messages and Queue Semantics

**Chapter:** Message broker  
**Topic:** Durable messages and queue semantics  
**Scope:** Enterprise Integration Patterns with Spring Integration, focusing on message storage, receiving and processing from queues, transactions, retries, errors, and correlation when building loosely coupled, extensible systems.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **durable/persistent messages**, **durable queues**, and **durable processing**; understand why each addresses a different type of failure.
- Explain queue semantics: producer/consumer, consumer competition, processing order, message retrieval timing, ACK/commit, redelivery, and delivery guarantees.
- Design Spring Integration flows with `QueueChannel` and a persistent `MessageStore`, or use brokers like RabbitMQ/Kafka when process separation is needed; control transactions, retries, idempotency, and error flows.
- Build test scenarios for restarts, crashes, duplicates, poison messages, and queue monitoring in an operational environment.

## 1. The problem: receiving a message does not mean processing succeeded

Suppose an ordering system emits an `OrderPlaced` event. The service puts a message onto a queue so workers can generate an invoice. When workers are busy or paused, the message needs to be retained. When the application or server restarts, messages that were **accepted but not yet processed** must still be available for continued processing.

An in-memory queue solves **rate decoupling** between sender and receiver, but does not by itself protect data from process termination. A queue with persistent storage helps data survive restarts, yet is still not enough to prevent **duplicate processing** or guarantee that a business task has completed.

Separate three questions:

1. **Does the message still exist?** Depends on where it is stored and when the system confirmed the write.
2. **Has the message been processed?** Depends on ACK, offset, transaction, or queue removal rules.
3. **How many times did the business effect occur?** Depends on idempotency and the consumer's transaction boundary.

## 2. Core terminology

| Concept | Meaning | Common misconception |
|---|---|---|
| **Durable queue** | Queue definition/configuration that survives a broker restart, depending on the technology. | A queue surviving does not mean every message inside it was durably written. |
| **Persistent/durable message** | A message written to a recoverable storage layer per the broker's or message store's mechanism. | A successful API-level send call does not necessarily mean a durable write confirmation was received from the broker. |
| **In-flight message** | A message delivered to a consumer or currently being processed, not yet confirmed complete. | Can be redelivered on timeout, rollback, connection loss, or crash. |
| **ACK/commit** | Signal ending the queue/broker's responsibility for a delivery or consumption position. | ACKing too early can lose work; ACKing late can lead to duplicates. |
| **Redelivery** | A message delivered again after the previous attempt did not complete per system rules. | Distinguish redelivery from creating a new message. |
| **Dead-letter queue (DLQ)** | Quarantine destination for messages that cannot be processed after retry policy exhaustion or unrecoverable errors. | Moving to a DLQ requires observability and follow-up handling. |
| **Idempotency** | Processing the same event multiple times still produces the same business result as processing it once. | This is a property of business logic, not a default property of a queue. |

**Note:** RabbitMQ, JMS, Kafka, and Spring Integration's `QueueChannel` store messages and confirm completion differently. Do not infer a specific technology's capabilities from the generic label “message broker”.

## 3. Queue flow and confirmation timing

~~~mermaid
flowchart LR
    P["Producer"] --> S["Send message"]
    S --> Q[("Durable queue / persistent store")]
    Q --> C["Consumer / Poller"]
    C --> H{"Business processing"}
    H -->|Success| A["ACK / commit"]
    H -->|Recoverable error| R["Rollback / retry with backoff"]
    H -->|Unrecoverable error| D["DLQ / quarantine"]
    R --> Q
~~~

The happy path typically means: producer sends → storage layer accepts → consumer receives → business logic runs → confirmation. **Actual policy depends on the queue type and transaction/acknowledgement configuration**; the diagram illustrates design intent and does not claim all brokers behave identically.

Three milestones to distinguish:

- **Producer accepted:** the send call was accepted by the sending layer or receiving layer; clarify whether a storage confirmation was obtained.
- **Consumer received:** a consumer was handed the message or polled it from the store; business logic is not necessarily finished yet.
- **Business committed:** business changes have been committed. At this point, coordinate ACK/transaction to avoid losing messages or uncontrolled reprocessing.

If the process stops **before the message is successfully persisted**, the producer needs a retry or outbox mechanism. If it stops **after business commit but before ACK**, the system may redeliver the message; the consumer must detect and skip duplicate effects.

## 4. Queue semantics: delivering to a worker group

### 4.1 Point-to-point and competing consumers

In point-to-point style, each message is distributed to be handled by one consumer in the group per delivery. If multiple workers read from the same queue, they **compete** for work; this is how throughput scales. “One consumer receives at a time” does not guarantee the business outcome happens *only once*, because a message can be redelivered.

In contrast, publish/subscribe typically broadcasts messages to multiple subscribers. To let each business group receive independently, design separate queues/subscriptions per technology. Multiple consumers reading from **one** work queue cannot be treated as multiple subscribers each receiving every message.

### 4.2 FIFO, concurrency, and completion order

FIFO (first in, first out) is generally the dequeue order in a simple queue. However:

- Two workers receiving messages A and B in order can still **finish B before A**.
- Retries, redeliveries, priorities, or multiple queues/partitions can alter observed order.
- Kafka only maintains record order **within a single partition**; there is no total order across a topic with multiple partitions.
- When business rules require per-order sequencing, attach `orderId` as a routing/correlation key and choose a key-based serialization strategy, or keep one consumer per ordering scope.

Do not rely on queue FIFO alone to guarantee data update ordering in a distributed system.

### 4.3 Backpressure and resource limits

Producers can send faster than consumers can process. Queues will grow, increasing latency, storage consumption, and potentially overloading the database or broker. Set appropriate limits: worker count, concurrent in-flight messages, prefetch/batch size, poller rate, queue quotas, and alerts on oldest message age. Behavior when a queue is full must be explicitly defined: wait, reject with backpressure, or route to an appropriate fallback.

## 5. Spring Integration: `QueueChannel` and message stores

Spring Integration provides `MessageChannel` to decouple sender/receiver components. With `QueueChannel`, consumers fetch messages using the `PollableChannel` model; a poller can pull messages and forward them to a `Service Activator` or handler.

| Option | Where does data live? | When to use? |
|---|---|---|
| Default `QueueChannel` | Process memory | Temporary buffer, simple application, acceptable to lose messages on process stop. |
| `QueueChannel` with `JdbcChannelMessageStore` | Database via JDBC | Need a durable queue within a Spring Integration application, with control over DB schema and transactions. |
| Spring Integration adapter to RabbitMQ/JMS | Out-of-process broker | Need cross-service communication, independent consumers, and broker queue/ACK mechanics. |
| Adapter to Kafka | Distributed log and consumer offsets | Need streaming, replay, consumer groups, retention, and per-partition ordering. |

An in-memory `QueueChannel` is **not durable by default**. To preserve messages across restarts, configure a compatible persistent message store and ensure the database is durably managed. Even a persistent message store does not replace the need for transactions when a consumer polls a message and executes business logic.

### 5.1 Example: JDBC-backed queue

The Java DSL example below illustrates a `QueueChannel` with a JDBC store and a transactional poller. Imports are omitted to focus on the main flow; this configuration requires Spring Integration JDBC/Java DSL libraries, a JDBC transaction manager, and Spring Integration table schemas matching your database type and version.

~~~java
@Configuration
@EnableIntegration
public class DurableOrderFlowConfig {

    @Bean
    JdbcChannelMessageStore orderMessageStore(DataSource dataSource) {
        JdbcChannelMessageStore store =
                new JdbcChannelMessageStore(dataSource);
        store.setRegion("orders");
        return store;
    }

    @Bean
    MessageChannel durableOrders(JdbcChannelMessageStore orderMessageStore) {
        return new QueueChannel(orderMessageStore, "order-events");
    }

    @Bean
    IntegrationFlow orderProcessingFlow(
            OrderService orderService,
            PlatformTransactionManager transactionManager) {

        return IntegrationFlow
                .from("durableOrders",
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(1000)
                                        .maxMessagesPerPoll(5)
                                        .transactional(transactionManager)))
                .handle(OrderEvent.class, (event, headers) -> {
                    orderService.applyOnce(event.eventId(), event);
                    return null;
                })
                .get();
    }
}

public record OrderEvent(String eventId, String orderId)
        implements java.io.Serializable {
}
~~~

Role of each component:

- `JdbcChannelMessageStore` persists messages in the database; `region` and group ID scope the queue, preventing data mixing across groups.
- `QueueChannel` uses the supplied message store instead of the default in-memory queue.
- `Pollers.fixedDelay(...)` sets the polling interval; `maxMessagesPerPoll` caps how many messages are processed per poll. Tune according to actual load.
- `transactional(transactionManager)` wraps the poll and processing in a transaction via poller advice. The transaction manager must match the **same JDBC resource** used by the message store; testing actual rollback and redelivery is mandatory.
- `orderService.applyOnce(...)` is an idempotent processing contract: the same `eventId` must not create two business effects. Its implementation depends on the database and must perform duplicate checks in the same transaction as business updates.

A producer can send a message into the channel as follows:

~~~java
public void publishOrder(MessageChannel durableOrders, OrderEvent event) {
    Message<OrderEvent> message = MessageBuilder
            .withPayload(event)
            .setHeader("eventId", event.eventId())
            .setHeader("correlationId", event.orderId())
            .build();

    boolean accepted = durableOrders.send(message);
    if (!accepted) {
        throw new IllegalStateException("Queue did not accept the message");
    }
}
~~~

A successful `send` call only reflects the channel's send contract at that instant. When the system must ensure **saving the order and emitting the message** do not diverge, use a transactional outbox or appropriate transaction mechanism; do not assume calling `send` after a database commit is atomic with the earlier write.

**Implementation checkpoints:** initialize JDBC Message Store tables using the script/schema matching your database; configure the transaction manager; set up serializers/message converters for payload and headers; maintain data compatibility when evolving `OrderEvent`; define access permissions and lifecycle for the message store. Writing Java objects directly into a JDBC store in this example is for illustration; in real systems, use an explicitly versioned event format.

### 5.2 Why wrap processing in a transaction?

A pollable queue can remove a message from the queue when a consumer takes it. If retrieval and business logic are not enclosed in an appropriate transaction/acknowledgement strategy, crashing right after receipt can lose the message before work finishes. With a transaction-capable persistent store, a rollback leaves the take uncommitted, allowing reprocessing.

Suppose invoice processing has two steps: updating status in the DB and then sending an email. A DB transaction can only roll back DB changes; an email already sent externally **cannot be rolled back by a DB transaction**. Therefore, idempotency or an outbox for external side effects is still needed even when message processing is transactional.

## 6. Delivery guarantees: choose the right assumption

| Guarantee | Typical behavior | Risks and requirements |
|---|---|---|
| **At-most-once** | Messages may be lost, with no redelivery attempt after failure. | Suitable for non-critical signals; insufficient for transactions that must be processed reliably. |
| **At-least-once** | System retries delivery until acknowledged or policy limit is reached. | Duplicate processing may occur; requires idempotent consumers. |
| **Exactly-once effect** | Final business impact is equivalent to processing once. | Scope must be clearly defined; typically achieved via transactions, unique keys, deduplication, and coordinated confirmation. |

Do not claim “exactly once” across multiple systems based solely on a single broker option. For example, a broker may prevent duplicate writes within its log, yet calling a payment API, sending an email, or writing to another database can still repeat when a consumer reruns.

### 6.1 Three crash points worth testing

| Crash point | What can happen | Mitigation |
|---|---|---|
| Before the system confirms the message is stored | Producer does not know whether the message was persisted. | Retry with a stable event key; use publisher confirms/outbox where needed. |
| After consumer takes the message, before business commit | Work may need to be redelivered, depending on ACK/transaction. | Align ACK/rollback boundaries properly; test redelivery. |
| After business commit, before ACK | Next processing attempt may repeat an already succeeded operation. | Idempotency keys and duplicate checks on business data. |

### 6.2 Idempotent processing with a business key

Use a stable producer-generated `eventId`, independent of internal message IDs. A common pattern is writing to a `processed_event` table with a unique constraint and updating business state **in the same transaction**:

~~~sql
-- PostgreSQL illustration; table processed_event has UNIQUE(event_id).
BEGIN;

INSERT INTO processed_event(event_id)
VALUES (:eventId)
ON CONFLICT (event_id) DO NOTHING;

-- Only perform the business update if the INSERT above
-- actually created a new row.
UPDATE orders
SET invoice_status = 'CREATED'
WHERE order_id = :orderId;

COMMIT;
~~~

The SQL illustrates the principle; the application must check the inserted row count and **skip the UPDATE when the insert did nothing because the event already existed**. If marking processed and updating business state happen in separate transactions, the consumer can leave partial state. For APIs outside the database, use the receiver's idempotency key or store pending commands in an outbox for re-coordination.

## 7. Retries, error channels, and poison messages

Transient errors like database timeouts can be retried; invalid data or schema violations usually need isolation. A pragmatic handling policy:

1. **Classify errors:** recoverable (timeouts, flaky network) vs. unrecoverable (schema mismatch, missing required fields).
2. **Bounded retries:** set max attempts, exponential backoff, and jitter; avoid immediate tight retry loops that cause congestion.
3. **Preserve correlation metadata:** `eventId`, `correlationId`, attempt count, failure reason, initial timestamp.
4. **Move to DLQ/quarantine:** when thresholds are exceeded or unrecoverable errors occur; handoff must not lose the message.
5. **Fix root cause then replay:** rerun only after data or handler issues are resolved, ensuring idempotency.

In Spring Integration, `errorChannel` routes `ErrorMessage`s to an error-handling flow, but **does not automatically imply durable retry or successful ACK**. Check whether exceptions raised by a handler propagate to the poller/adapter or are absorbed by an error handler; this choice determines transaction rollback and broker reaction. Do not configure an error handler that just logs and swallows exceptions when you expect the broker to redeliver.

When using an external broker:

- **RabbitMQ:** typically requires a declared durable queue, persistent messages, and appropriate publish/consume confirmations. ACK/requeue and DLX/DLQ are separate mechanisms; configurations must be tested against a real broker.
- **JMS:** persistent delivery and transaction/session acknowledgment depend on the provider and listener configuration.
- **Kafka:** messages are retained in the log per retention policy; consumers commit offsets to track read position. This is not traditional work-queue dequeue/delete. Retries, dead-letter topics, and per-partition ordering must be designed explicitly.

## 8. Correlation, tracing, and observability

At minimum, a message should carry an **immutable event ID** for deduplication, a **business key** (e.g., `orderId`) for correlation, and a **trace context** to link logs across Router, Transformer, Service Activator, and broker adapter steps. Do not use an auto-generated message ID as a uniqueness guarantee for the same business event across retries or republishes.

Key operational metrics include:

- Pending message count, in-flight message count, and **oldest message age**.
- Enqueue/dequeue rate, time from publish to processing, active consumer count, and per-poll latency.
- Retry counts, errors by cause, DLQ depth, blocked duplicate rate, and recovery time after restart.
- Store capacity, database/broker latency, message write failures, and connection status.

Set alerts around business objectives. For instance, a queue with 10,000 messages that drains rapidly may be less severe than a queue with 100 messages waiting past the processing SLA.

## 9. Choosing a persistent QueueChannel or an external broker?

**Use a persistent `QueueChannel`** when the application needs internal producer/consumer decoupling at moderate volume, can manage a JDBC store, and does not need complex broker topology. Thoroughly test throughput, contention, table size, and transactions when scaling across multiple instances.

**Use RabbitMQ/JMS** when independent services must communicate over queues and want to leverage routing, consumer management, ACKs, DLQs, and broker operations. **Use Kafka** when the workload is an event stream requiring retention/replay, multiple consumer groups, and key/partition ordering. An application can still use Spring Integration as the wiring layer for Routers, Transformers, Gateways, and Error Channels around those adapters.

Do not choose solely based on the word “durable”. Write out the failure model explicitly: *which failures must be tolerated, which data must never be lost, how duplicates are handled, how far back replay is needed, and where business completion is confirmed*.

## 10. Practice and behavior testing

Suppose `order-42` emits event `evt-123`; a worker updates `invoice_status`. Run the flow from the JDBC example and test these scenarios:

| Scenario | Action | Expected result |
|---|---|---|
| Producer sends while worker is paused | Enqueue `evt-123` without starting the poller right away. | Message remains in the persistent store and is processed once the poller starts. |
| Restart before processing | Stop and restart the application after enqueue commits. | Message can be retrieved and processed after restart. |
| Failure mid-processing | Make the handler throw an exception before commit. | Verify transaction rollback and redelivery per actual config; no false success marked. |
| Crash after business commit, before ACK | Simulate redelivery of the same `evt-123`. | `applyOnce` prevents duplicate invoice/side effect creation. |
| Poison message | Send an invalid payload repeatedly. | Bounded retry, moved to quarantine/DLQ, with logs/correlation for investigation. |
| Multiple workers | Increase consumers and emit events A and B with the same `orderId`. | Do not assume completion order; apply key-based ordering if required. |
| Store/broker connection loss | Disconnect the database or broker during publish and during consume. | Send/receive reports clear errors; never silently confirms when not saved or processed. |

One way to measure practice results is to count **business side effects** after re-running the same `eventId`, rather than just counting how many times the handler ran. A handler may run twice under at-least-once delivery; the final state must still be correct and must not produce two invoices.

## 11. Pre-production checklist

- [ ] Clearly identify where messages are durably persisted and what condition proves the producer is confirmed.
- [ ] Verify queue, message, database/broker durability and technology-specific recovery mechanisms.
- [ ] Verify transactions/ACKs wrapping message receipt and processing; simulate crashes at critical milestones.
- [ ] Use a stable `eventId`, deduplication, and idempotency on all critical side effects.
- [ ] Have retry/backoff policies, DLQ/quarantine, safe replay procedures, and designated owners.
- [ ] Document ordering, correlation, concurrency, and capacity requirements.
- [ ] Monitor queue lag, message age, duplicates, errors, and storage layer health.
- [ ] Test restarts, failover, duplicate handling, and payload version changes before deployment.

**Conclusion:** durable messages protect **pending data**; queue semantics govern **who receives a message and what happens on failure**; transactions, ACKs, and idempotency protect **business outcomes**. Combining these three layers properly yields reliable Spring Integration message flows under retries, restarts, and multiple consumers.
