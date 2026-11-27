# Source Message ID and Duplicate Detection

In Spring Integration, a producer creates a `Message<?>` and sends it to a channel for downstream endpoints to process. Each message has a technical identifier managed by Spring, but that identifier alone does not solve the problem of a single business event being emitted or delivered multiple times. For reliable duplicate detection, producers and consumers must agree on a key representing **the same business event**.

## 1. Distinguishing Message ID and Event ID

`Message<T>` is an envelope containing a payload and headers. When constructing a message, Spring Messaging automatically generates `id` and `timestamp` headers. `id` is typically a UUID used to identify a single message instance in logs, traces, or flow diagnostics. `timestamp` records when the message was created.

These two values carry technical meaning:

- `id` answers: "Which message instance is this?"
- `timestamp` answers: "When was this message instance created?"

They do not necessarily answer: "Is this the same order event I processed earlier?" For instance, a producer receives the same `OrderCreated` event twice and builds two new `Message` objects. Each message can have a different `id` even though the payload describes the exact same order and the exact same event.

Therefore, the application should carry a stable key supplied by the business domain or source system, commonly called `eventId`, `idempotencyKey`, or an equivalent name. This key must remain unchanged when the same event is retried, replayed, or redelivered.

| Value | Meaning | Used for |
| --- | --- | --- |
| `MessageHeaders.id` | Framework-generated identifier of a message instance | Logging, tracing, investigating a single message transmission |
| `eventId` / `idempotencyKey` | Stable identifier of a business event | Duplicate detection and idempotent processing |
| `correlationId` | Identifier of a group of messages belonging to the same conversation or workflow | Linking request/reply, sagas, or related messages |
| `sequenceNumber` / `sequenceSize` | Position and size of an ordered group of messages | Aggregating or processing a message sequence |

Do not use `correlationId` as a substitute for `eventId`: multiple distinct events can belong to the same workflow. Likewise, `sequenceNumber` only describes position within a sequence, not the unique key of an event.

## 2. Creating Messages with a Stable Key at the Producer

The producer should take the key from the source event or generate and persist the key once before publishing the event. If the producer generates a new UUID on every retry, consumers will see different keys and fail to recognize it as the same event.

Example of a producer converting an order event into a Spring message:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public record OrderCreated(
        String eventId,
        String orderId,
        String customerId) {
}

public Message<OrderCreated> toMessage(OrderCreated event) {
    return MessageBuilder.withPayload(event)
            .setHeader("eventId", event.eventId())
            .setHeader("sourceSystem", "order-service")
            .build();
}
```

When `build()` creates the message, Spring assigns `MessageHeaders.id` for the message instance. The `eventId` header preserves the stable business identifier. If the same `OrderCreated` is replayed, the producer must reuse the original `eventId`.

In systems receiving messages from a broker or adapter, headers containing the broker's ID may be mapped from transport metadata. For example, an adapter may supply a message ID, partition, offset, or transport-specific delivery metadata. Exact names and mapping depend on the adapter. Do not assume the broker ID is always identical to `MessageHeaders.id`, or that it is preserved across every message transformation step. When source correlation is needed, store transport metadata in explicitly named headers and keep the business `eventId` separate.

## 3. Why Are Messages Delivered as Duplicates?

Duplicates can arise during normal operation in distributed systems:

- The producer sends successfully but misses the confirmation due to a timeout, so it resends.
- The broker redelivers a message when a consumer fails to acknowledge, shuts down, or rolls back processing.
- A consumer performs the business side effect but fails before acknowledging the message; the next delivery runs the same event again.
- Operators replay messages to recover or backfill data.
- Multiple consumers receive or process an event concurrently due to subscription configuration, retries, or failover.

Therefore, you cannot rely solely on the producer "sending only once" or the consumer "usually receiving only once." The system should assume the same event can arrive multiple times and design business operations to be idempotent.

## 4. Duplicate Detection Using Keys and MetadataStore

A common approach in Spring Integration is storing accepted keys in a `MetadataStore`. For concurrent processing across multiple threads or instances, use an implementation supporting atomic operations such as `ConcurrentMetadataStore.putIfAbsent(key, value)`. The return value indicates whether the key already existed: only one execution can claim the key within the shared store scope.

The example below illustrates an inbound check. `metadataStore` is a `ConcurrentMetadataStore` configured for the application:

```java
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.messaging.Message;

public boolean isFirstDelivery(
        Message<?> message,
        ConcurrentMetadataStore metadataStore) {

    Object rawEventId = message.getHeaders().get("eventId");
    if (rawEventId == null || rawEventId.toString().isBlank()) {
        throw new IllegalArgumentException("Message is missing eventId");
    }

    String key = "order-created:" + rawEventId;
    return metadataStore.putIfAbsent(key, "PROCESSING") == null;
}
```

If the method returns `true`, the message claimed the key and can proceed to processing. If it returns `false`, the key was already recorded; the consumer should apply the chosen duplicate policy, such as logging and skipping, incrementing a metric, or routing the message to an inspection flow. The `order-created:` prefix namespaces keys so different event types do not collide.

Spring Integration also provides the Idempotent Receiver pattern, including `IdempotentReceiverInterceptor` and a metadata-store-based selector, to mark duplicate messages at endpoints. This mechanism is useful when you want to embed the check rule in endpoint configuration. Configure the selector using a stable business key and clearly decide whether the handler skips, logs, or processes messages marked as duplicates.

## 5. Placing Duplicate Detection at the Right Transaction Boundary

An atomic `putIfAbsent` operation only solves claiming processing rights for the key. It does not by itself guarantee the business effect happens only once under all failure scenarios.

For example, if you mark the key as processed first and the application crashes before updating the order, redelivery will be skipped even though the business update never completed. If you mark the key only after updating the order, two concurrent consumers could both apply the update before either writes the key.

When the metadata store and business data share a transactional database, key insertion and business updates can be placed inside the same transaction. Conceptual example:

```java
public boolean handleOnce(Message<OrderCreated> message) {
    String eventId = (String) message.getHeaders().get("eventId");
    if (eventId == null || eventId.isBlank()) {
        throw new IllegalArgumentException("Message is missing eventId");
    }

    String key = "order-created:" + eventId;
    return transactionTemplate.execute(status -> {
        if (metadataStore.putIfAbsent(key, "DONE") != null) {
            return false; // Event was already committed previously.
        }

        orderService.apply(message.getPayload());
        return true;
    });
}
```

This snippet assumes `metadataStore` and `orderService` participate in the same transaction manager and commit boundary. When `orderService.apply` fails, the transaction rolls back both the business change and the key; on commit, both are persisted. If the metadata store and business data reside in separate systems without a shared transaction, this snippet does not provide atomicity. In that case, use an inbox/outbox pattern, idempotent business operations, or a recovery protocol suited to the architecture.

For multi-step processing, you can store states such as `PROCESSING`, `COMPLETED`, and lease/expiration metadata to recover abandoned executions. Clearly define when retries are allowed, how expired leases are detected, and how two workers are prevented from resuming the same work concurrently. Never leave a `PROCESSING` status stuck permanently after a failure.

## 6. Choosing Key Storage Location and Retention Duration

The scope of the metadata store determines the scope of duplicate detection:

- An in-memory store inside a single process only protects that instance; restarts lose data and other instances cannot see the keys.
- A shared, durable store—such as an implementation backed by JDBC or Redis suited to the infrastructure—coordinates across multiple instances and preserves state across restarts.
- When using a distributed store, verify atomic operation semantics, durability, transactions, consistency, and behavior when the store is temporarily unreachable.

Keys also need an expiration policy. Retaining them for too short a window can cause late replays to be treated as new; retaining them indefinitely causes unbounded metadata growth. Retention duration should be based on the retry window, how long the broker can redeliver, replay policies, and business requirements. If old events can be replayed months later, retain markers longer or enforce uniqueness constraints directly in business data.

Do not delete a key merely because the consumer received or sent an ACK with the broker. Broker ACK and business commit are separate events; their ordering must align with the system's transaction and recovery design.

## 7. Observing and Diagnosing Duplicates

When logging or tracing a processing attempt, record both `MessageHeaders.id` and `eventId`, along with the channel/endpoint name, message source, duplicate check outcome, and transaction status. This distinguishes two separate message instances representing the same event from a single message instance followed across multiple endpoints.

Signals to monitor include:

- Rate of messages marked as duplicates by producer, event type, and endpoint.
- Retry/redelivery counts, number of keys currently in `PROCESSING` state, and their age.
- Errors or latency when reading/writing the metadata store.
- Events missing `eventId`, unusual key contention, or rapid key growth.
- Discrepancies among messages received, new events, duplicate events, and committed business updates.

Avoid using `eventId` as a high-cardinality metric label. Log it in a controlled manner for looking up specific events, while grouping metrics by event type, endpoint, or processing outcome.

## 8. Implementation Verification Procedure

1. Identify a specific business event and where `eventId` is generated; confirm the key stays constant across retries and replays.
2. Create two separate messages for the same event. Verify `MessageHeaders.id` can differ while `eventId` stays identical.
3. Send two copies of the same event concurrently through the endpoint. Only one execution may apply the business side effect.
4. Force the consumer to fail before commit and redeliver the message. Verify the key and business data roll back together or recover as designed.
5. Restart the application or run across two instances to verify the store has the expected scope and durability.
6. Replay an event after longer than the expected retry window to verify retention policies.

Once these conditions are verified, the message ID supports tracing each message instance, while the idempotency key protects business effects against duplicate delivery. These two identifiers complement each other and should be tracked separately in the Spring Integration runtime.
