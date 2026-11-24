# Distinguishing Business Ordering from Delivery Ordering in Spring Messaging

In a messaging system, two messages may be sent in one order yet received, processed, or committed in a different order. Therefore, you must separate **business ordering** defined by the application domain from **delivery ordering** produced by the transport, broker, channels, and consumers.

For example, in an order lifecycle, business rules require `OrderCreated` to happen before `PaymentAuthorized`, and only then `OrderShipped`. A consumer might receive sequence 1, 3, 2 because the second event was delayed or retried. If event 3 is applied immediately upon receipt, the order state becomes corrupted even though all messages eventually arrived.

## 1. Two Concepts and Distinct Ordering Milestones

**Business ordering** is the valid order according to domain rules: which state transitions are allowed first, which event depends on which event, and which version of an aggregate must be applied first. This order should be represented explicitly via rules or logical sequence numbers, typically a per-aggregate sequence/version such as `orderId`.

**Delivery ordering** is the order in which messages pass through technical stages. In practice, distinguish at least the following milestones:

| Milestone | Meaning | What It Does Not Automatically Prove |
| --- | --- | --- |
| Publish order | Order in which the producer emits messages | That the broker or consumer will necessarily observe that same order |
| Broker/queue order | Order in which the broker accepts or enqueues messages | That multiple consumers will finish processing in that order |
| Receive order | Order in which the client/consumer reads messages | That handlers or transactions will complete in that order |
| Handling start order | Order in which handlers begin processing | That concurrent tasks will finish in that order |
| Completion order | Order in which asynchronous processing finishes | That data has durably committed in that same order |
| Commit order | Order in which state changes are durably persisted | That downstream systems have received and applied the same order |

An application can claim to "preserve order" only when it specifies at which milestone order is preserved and within what scope: a session, a connection, a queue, a partition, an aggregate, or the entire system.

Example of a valid business sequence:

```text
Business sequence of order-42
1. OrderCreated
2. PaymentAuthorized
3. OrderShipped

Order received by consumer
1. OrderCreated
3. OrderShipped  <- arrived early due to processing/retry/different path
2. PaymentAuthorized
```

Receiving event 3 does not mean the business domain is ready to apply it. The consumer must check the sequence or state preconditions before mutating data.

## 2. Why Can Delivery Order Differ from Business Order?

- **Multiple producers:** two producers emitting events for the same aggregate can race and have no global order without synchronization or a sequence assigned where state is written.
- **Executors and thread pools:** messages arrive sequentially yet are dispatched to multiple workers. A worker taking longer may finish after the worker handling the next message.
- **Concurrent consumers:** multiple consumers or subscriptions process independently; reading order from a queue does not imply completion order.
- **Retries and redelivery:** an older event may be redelivered after a newer event has arrived; delayed messages or messages routed through a dead-letter flow can return late.
- **Different broker partitions or queues:** independent message groups share no common total order. Brokers usually guarantee ordering only within the scope documented by the broker.
- **Reactive concurrency:** `flatMap` can run multiple inner publishers concurrently and interleave results as they complete.
- **Multiple connections/sessions:** ordering within one connection creates no shared order across different clients or producers.

TCP preserves byte order within a single TCP connection. However, the application may hand read messages off to executors, multiple threads, or reactive pipelines. Thus, byte order on a socket does not guarantee handler completion order or database commit order. Nor can a global order be inferred across multiple connections.

## 3. Spring Messaging and Message Ordering

Spring represents messages with `Message<T>` consisting of a payload and headers; `MessageChannel` decouples producers from consumers. A channel or broker is a transport/dispatch mechanism. The contracts of `Message` and `MessageChannel` do not automatically create business sequences, sort events by aggregate rules, or guarantee consumer transactions have committed.

The `MessageHeaders.ID` header identifies a message; `MessageHeaders.TIMESTAMP` records when the message was created. They are useful for tracing and observability, but do not replace a business sequence: timestamps can collide, machine clocks skew, messages may be created on multiple nodes, and retries can arrive late. Nor does an ID express which event must precede another.

### 3.1. STOMP over WebSocket: Preserving Receive Order and Publish Order

In STOMP, Spring typically uses `clientInboundChannel` to receive messages from WebSocket clients, `brokerChannel` to pass messages from server-side code to the broker, and `clientOutboundChannel` to send messages back to WebSocket clients. Inbound/outbound channels may use executors. When multiple tasks run on a thread pool, the order in which handlers run or clients receive messages may differ from the original order.

Spring Framework provides two separate options:

| API | Configuration Location | Scope Where Order Is Preserved |
| --- | --- | --- |
| `StompEndpointRegistry.setPreserveReceiveOrder(true)` | `registerStompEndpoints` | Messages from the same client session are dispatched into `clientInboundChannel` one by one in receive order. Available since Spring Framework 6.1. |
| `MessageBrokerRegistry.setPreservePublishOrder(true)` | `configureMessageBroker` | Messages sent to the same client session via `clientOutboundChannel` are published one by one in publish order. Available since Spring Framework 5.1. |

Example configuring both directions:

```java
@Configuration
@EnableWebSocketMessageBroker
public class StompOrderConfiguration implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
        registry.setPreserveReceiveOrder(true);
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setApplicationDestinationPrefixes("/app");
        registry.setPreservePublishOrder(true);
    }
}
```

This configuration illustrates Spring Framework 6.1 or later because it uses `setPreserveReceiveOrder`. `setPreservePublishOrder` has been available since Spring Framework 5.1. These two flags address two different directions: messages sent inbound by clients and messages sent outbound by the server/broker. Enable only the flag matching the problem you face.

These flags carry a performance cost because they reduce concurrency within a session. They only preserve order within the same session on their respective channels; they do not establish global order across sessions, sort events by `orderId`, fix producers emitting out of order, or replace domain sequences/versions.

### 3.2. RSocket and Concurrent Requests

RSocket supports multiple interaction models such as Request-Response, Request-Stream, Channel, and Fire-and-Forget. Many independent requests may run concurrently. The response to an earlier request may finish after the response to a later request if processing times differ. Do not infer business order from the completion order of concurrent requests.

- On a `Flux`, `concatMap` subscribes to and processes inner publishers sequentially, preserving input element order and preventing inner publishers from interleaving.
- `flatMap` lets inner publishers run concurrently and merges results as they emit; unsuitable when side effects must execute sequentially.
- `flatMapSequential` may subscribe to inner publishers concurrently while queuing outputs to emit in input order. It preserves output order, yet inner work can still run in parallel; do not treat it as a guarantee that side effects occurred sequentially.

Example processing commands sequentially within a single stream:

```java
Flux<OrderCommand> commands = receiveCommands();

Flux<OrderResult> results = commands.concatMap(orderService::apply);
```

This is an illustrative snippet; `receiveCommands()` and `orderService` are application-supplied. `concatMap` serializes subscriptions and waits for the current command's publisher to complete before processing the next one. If commands belong to independent aggregates, you can process across aggregates in parallel while keeping operations sequential within each aggregate.

## 4. Designing Business Ordering with Sequence/Version

When events for an aggregate must be applied in order, include that order in the message contract. An event typically includes fields such as:

| Field | Purpose |
| --- | --- |
| `eventId` | Unique identifier to detect and deduplicate redeliveries |
| `aggregateId` | Business object key affected by the event, e.g., `orderId` |
| `sequence` or `aggregateVersion` | Monotonically increasing sequence number within the aggregate scope |
| `eventType` | Event type, e.g., `PaymentAuthorized` |
| `occurredAt` | Business occurrence timestamp for auditing/observability |
| `correlationId` / `causationId` | Links interaction chains and the cause that produced the event |

`sequence` must be assigned at the authoritative place that writes aggregate state. If multiple producers generate sequences independently using clocks or local counters, duplicate numbers or inconsistent ordering can result. Typically, update the version and write the event within the same database transaction.

Contract example:

```json
{
  "eventId": "evt-9003",
  "aggregateId": "order-42",
  "sequence": 3,
  "eventType": "OrderShipped",
  "occurredAt": "2026-11-07T10:15:30Z"
}
```

A sequence typically only needs to be unique and contiguous within a single aggregate. There is no need to force all orders, accounts, or sessions onto one global counter. Partitioning by aggregate allows parallel processing across independent objects while maintaining exact order per object.

### 4.1. Consumer Rules When Receiving Events

Suppose the consumer has applied up to sequence 1 and receives sequence 3:

1. If `sequence` is less than or equal to `lastAppliedSequence`, treat it as a duplicate or late arrival; safely ignore after confirming the event has already been processed.
2. If `sequence == lastAppliedSequence + 1`, apply the event and increment `lastAppliedSequence` in the same transaction as the business update.
3. If `sequence > lastAppliedSequence + 1`, a gap is detected. Temporarily buffer the event, wait for the missing event, request a replay from the source, or escalate to a reconciliation workflow.
4. If the gap is not filled within the policy window, raise an alert and place the aggregate in a pending-handling state. Do not arbitrarily apply later events if doing so breaks business invariants.

Buffers must have bounded capacity and wait timeouts. If event 2 never arrives, holding event 3 indefinitely can cause memory leaks or stall a partition. Policies for timeouts, replay, dead-lettering, alerting, and controlled recovery are required.

### 4.2. Java 17 Example: Preserving Order by Sequence

The program below simulates a consumer for a single aggregate. Event 3 arriving before event 2 is buffered; when event 2 arrives, the consumer applies 2 and then 3 in order. A later redelivery of event 2 is detected as a duplicate/late arrival.

**OrderSequenceDemo.java**

```java
import java.util.NavigableMap;
import java.util.TreeMap;

record OrderEvent(String orderId, long sequence, String type) { }

public class OrderSequenceDemo {

    static final class Processor {
        private final String orderId;
        private long nextSequence = 1;
        private final NavigableMap<Long, OrderEvent> pending = new TreeMap<>();

        Processor(String orderId) {
            this.orderId = orderId;
        }

        void accept(OrderEvent event) {
            if (!orderId.equals(event.orderId())) {
                throw new IllegalArgumentException("Unexpected aggregate");
            }

            if (event.sequence() < nextSequence) {
                System.out.printf("Ignored duplicate/late %s #%d%n",
                        event.orderId(), event.sequence());
                return;
            }

            OrderEvent previous = pending.putIfAbsent(event.sequence(), event);
            if (previous != null) {
                System.out.printf("Ignored duplicate pending %s #%d%n",
                        event.orderId(), event.sequence());
                return;
            }

            if (event.sequence() > nextSequence) {
                System.out.printf("Buffered %s #%d %s; waiting for #%d%n",
                        event.orderId(), event.sequence(), event.type(), nextSequence);
                return;
            }

            drain();
        }

        private void drain() {
            OrderEvent event;
            while ((event = pending.remove(nextSequence)) != null) {
                System.out.printf("Applied %s #%d %s%n",
                        event.orderId(), event.sequence(), event.type());
                nextSequence++;
            }
        }
    }

    public static void main(String[] args) {
        Processor processor = new Processor("order-42");
        processor.accept(new OrderEvent("order-42", 1, "OrderCreated"));
        processor.accept(new OrderEvent("order-42", 3, "OrderShipped"));
        processor.accept(new OrderEvent("order-42", 2, "PaymentAuthorized"));
        processor.accept(new OrderEvent("order-42", 2, "PaymentAuthorized"));
    }
}
```

Compile and run with Java 17:

```bash
javac OrderSequenceDemo.java
java OrderSequenceDemo
```

Exact output:

```text
Applied order-42 #1 OrderCreated
Buffered order-42 #3 OrderShipped; waiting for #2
Applied order-42 #2 PaymentAuthorized
Applied order-42 #3 OrderShipped
Ignored duplicate/late order-42 #2
```

This example uses an in-memory `TreeMap` to illustrate the algorithm, not as a production implementation. Real applications must persist `lastAppliedSequence` and pending events durably, guard concurrent processing for the same aggregate, and update the sequence alongside side effects in a transaction. If the application restarts, the in-RAM buffer in this example is lost.

## 5. Deployment Patterns in Distributed Systems

### 5.1. Partitioning by Aggregate or Ordering Key

Send events sharing the same `aggregateId` to the same partition, queue group, or consumer lane as supported by the broker. When the broker guarantees ordering within that scope, consumers can process sequentially per key and in parallel across keys. Exact names and guarantees depend on the broker; Spring Messaging does not define partition semantics on its own.

Do not use a single consumer for the entire system just to get global order if the business only requires per-aggregate order. A single global stream reduces throughput and allows one slow message to block unrelated messages.

### 5.2. Transactional Outbox

When a transaction updates an order and emits an event, write the business change together with an outbox record in the same database transaction. A publisher reads the outbox and sends events after commit.

The outbox avoids situations where the database commits but the event is never emitted, or an event is emitted even though the business transaction rolled back. However, an outbox alone does not guarantee publish order: the publisher must still read and send events in aggregate sequence order, prevent multiple workers from publishing the same aggregate concurrently, and use an appropriate ordering key/partition on the broker.

### 5.3. Idempotency and Duplicate Message Handling

Brokers or transports may redeliver messages when acknowledgements are lost, consumers restart, or retries happen. Consumers should record processed `eventId` values or check sequence/version so an event never applies side effects twice. Recording processed status and updating aggregate state must be committed atomically.

If a consumer commits to the database before sending ACK and the ACK is lost, the message may be redelivered; deduplication ensures redelivery causes no second side effect. If it ACKs before committing and crashes between the two steps, the message can be lost from the pipeline even though business state was never saved. ACK timing must match broker and transaction semantics.

### 5.4. Handling Missing or Very Late Events

When a sequence gap is detected, the system can wait briefly, request a replay from the publisher, re-read the event log, or route the aggregate to a reconciliation queue. Policy must clearly define which events may be skipped and who has authority to approve skipping. For events representing irreversible state transitions, sorting by timestamp or applying only the latest event is usually unsafe.

## 6. Choosing the Appropriate Guarantee Level

| Need | Approach | Trade-off |
| --- | --- | --- |
| Preserve client-sent order within a STOMP session | `setPreserveReceiveOrder(true)` | Reduces inbound concurrency within that session |
| Preserve server-published order to a STOMP session | `setPreservePublishOrder(true)` | Reduces outbound concurrency within that session |
| Preserve side-effect order in a reactive sequence | `concatMap` | Inner publishers run sequentially, reducing concurrency |
| Preserve output order while allowing concurrent inner execution | `flatMapSequential` | May buffer results; side effects can still finish out of order |
| Preserve event order per order/account | Per-aggregate sequence/version and sequential per-key consumer | Requires storing sequences, deduplicating, handling gaps, and managing concurrency |
| Preserve global order across all messages | Single sequential stream or dedicated total-ordering mechanism | Low throughput, prone to bottlenecks; usually unnecessary |

Before enabling an ordering mechanism, identify the scope that needs protection. If only per-order ordering is required, global ordering is overkill. If clients need to observe messages in server publish order, database business sequences alone do not stop an outbound executor from sending out of order; appropriate transport configuration is also needed.

## 7. Investigation Process When Messages Arrive Out of Order

1. **Identify the business definition.** Which event must precede which? Is the scope one aggregate, one session, one user, or the entire system?
2. **Record timestamps and sequences.** Log `eventId`, `aggregateId`, `sequence`, `occurredAt`, and timestamps for publish, receive, handler start/end, and commit. Use `sequence` to verify business order; timestamps help observe latency.
3. **Locate where order diverges.** Compare producer output, broker enqueue/partition, consumer receive, handler completion, and database commit.
4. **Inspect concurrency.** Check executor sizes, consumer counts, subscriptions, reactive operators (`flatMap`, `concatMap`), and connection/session counts.
5. **Check retries and duplicates.** An older event may be redelivered after a newer one. Cross-check event IDs, attempt counts, retry delays, and dead-letter/replay paths.
6. **Check STOMP if using WebSockets.** Determine whether inbound or outbound ordering is needed; check whether `setPreserveReceiveOrder` and `setPreservePublishOrder` are enabled in the right places.
7. **Verify state transitions.** Does the consumer check `sequence == lastAppliedSequence + 1` before committing? Are the sequence and side effects updated atomically?
8. **Test failure scenarios.** Send events 1, 3, 2; resend event 2; slow down event 1's handler; restart the consumer between commit and ACK. Confirm the final state is correct with no duplicate side effects.

## 8. Common Misconceptions

- **"TCP/WebSocket preserves order, so the application is always in order."** TCP preserves byte order within one connection; executors, multiple sessions, multiple consumers, and async commits can still scramble processing order.
- **"Enabling `setPreservePublishOrder` preserves business order."** That flag preserves publish order to the same STOMP session; it does not verify business sequences.
- **"A message with a newer timestamp must be processed later."** Timestamps are not logical sequences, clocks can skew, and timestamps do not describe causality.
- **"`flatMapSequential` makes side effects sequential."** The operator preserves output emission order, yet can run inner publishers concurrently.
- **"Sending a message successfully means business logic committed."** A `send` result at one layer speaks only to that layer. Confirming business completion requires an ACK/reply or durable state per the application contract.
- **"A single consumer solves everything."** It can create a global bottleneck and still fails to fix out-of-order producers, duplicates, or retries.
- **"Exactly-once delivery solves ordering automatically."** Delivery guarantees and ordering are distinct properties. The system still needs sequences, idempotency, and proper transactions.

## 9. Key Takeaways

- Business ordering is defined by the domain; delivery ordering is produced by technical layers.
- Distinguish publish, receive, handling, completion, and commit order before claiming a pipeline preserves order.
- Spring STOMP provides `setPreserveReceiveOrder` (since 6.1) and `setPreservePublishOrder` (since 5.1), both scoped to a single client session.
- Reactor `concatMap` serializes inner publishers; `flatMap` allows interleaving; `flatMapSequential` preserves output order while still running inner publishers concurrently.
- Use per-aggregate sequences/versions so consumers can detect duplicates and gaps; do not substitute timestamps.
- Combine partition/ordering keys, transactional outbox, deduplication, transactions, and replay to protect ordering in distributed systems.

## References

- [Spring Framework Reference — Order of Messages (STOMP)](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html)
- [Spring Framework Reference — Flow of Messages (STOMP)](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework API — MessageBrokerRegistry](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/config/MessageBrokerRegistry.html)
- [Spring Framework API — StompEndpointRegistry](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/config/annotation/StompEndpointRegistry.html)
- [Reactor Core API — Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)