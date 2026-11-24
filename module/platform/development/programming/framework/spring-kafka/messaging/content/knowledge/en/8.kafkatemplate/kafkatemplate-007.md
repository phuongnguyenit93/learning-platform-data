# Receiving CompletableFuture from Send Operations

## 1. Why does KafkaTemplate return CompletableFuture?

The Kafka producer is designed to send records asynchronously. When an application calls `KafkaTemplate.send()`, the producer accepts the record, serializes the key/value, places the record into a buffer, and sends it to the broker via a background I/O thread. The application does not have to wait for the broker at the call site.

Spring Kafka exposes the send result as a `CompletableFuture<SendResult<K, V>>`. The future represents an in-flight or completed send operation. When the producer completes the operation according to the configured `acks`, the future completes normally with a `SendResult`; if sending fails, the future completes exceptionally. With `acks=0`, the producer does not wait for a broker acknowledgement, so the guarantee is weaker.

```text
OrderService
    |
    | KafkaTemplate.send("orders", orderId, event)
    v
KafkaTemplate / KafkaProducer
    |                            \
    | returns CompletableFuture   \ sends via I/O thread
    v                              v
OrderService continues        Kafka broker
                                   |
                                   | acknowledgement or error
                                   v
                            completes CompletableFuture
                                   |
                                   v
                          callback / future continuation
```

The future decouples the time a request is submitted from the time its outcome is received. The business layer can return the future to the caller, register callbacks, transform the result, or compose multiple asynchronous operations.

## 2. Return type from send()

In Spring Kafka 3.0 and later, `KafkaTemplate.send()` overloads return `CompletableFuture<SendResult<K, V>>`. Older Spring Kafka versions use `ListenableFuture`; when working with legacy projects, verify the exact version's API instead of assuming the return type is always `CompletableFuture`.

Example declaring the future type:

```java
CompletableFuture<SendResult<String, OrderCreated>> future =
        kafkaTemplate.send("orders", "ORD-100", event);
```

Where:

- `String` is the record key type.
- `OrderCreated` is the value type before the serializer converts it to bytes.
- `SendResult<String, OrderCreated>` contains the sent record and the metadata returned by the broker.

`SendResult` holds two important pieces of information:

| Method | Value | Usage |
|---|---|---|
| `getProducerRecord()` | The `ProducerRecord<K, V>` that was sent | Inspect topic, key, value, specified partition, and headers |
| `getRecordMetadata()` | `RecordMetadata` from the Kafka broker | Obtain topic, partition, offset, timestamp, and serialized record sizes |

The offset in `RecordMetadata` is meaningful only within its corresponding partition. Do not use the offset alone as a cluster-wide unique event ID; maintain an application-generated `eventId` for business tracing.

## 3. Obtaining the future from KafkaTemplate overloads

Send overloads differ in input parameters, yet all return a future holding a `SendResult`:

```java
// Topic and value
CompletableFuture<SendResult<String, OrderCreated>> a =
        kafkaTemplate.send("orders", event);

// Topic, key, and value
CompletableFuture<SendResult<String, OrderCreated>> b =
        kafkaTemplate.send("orders", event.orderId(), event);

// Topic, partition, key, and value
CompletableFuture<SendResult<String, OrderCreated>> c =
        kafkaTemplate.send("orders", 2, event.orderId(), event);

// ProducerRecord can carry timestamp, headers, and partition
ProducerRecord<String, OrderCreated> record =
        new ProducerRecord<>("orders", event.orderId(), event);
CompletableFuture<SendResult<String, OrderCreated>> d =
        kafkaTemplate.send(record);
```

The examples show common overloads. If only topic and value are supplied, the partitioner selects the partition. If a key is supplied, the partitioner usually uses the key to select a partition. If a partition is specified directly, the application is responsible for ensuring that partition exists.

With Spring Messaging's `Message<?>` or `sendDefault()` overloads, the future likewise represents the send result and uses generic types matching `KafkaTemplate`'s key/value types.

## 4. Registering a callback with whenComplete()

`whenComplete()` registers an action that runs when the future completes, whether successfully or exceptionally. The callback receives two parameters: the result and the exception. On success, the exception is `null`; on failure, the result is normally `null`.

```java
public record OrderCreated(
        String eventId,
        String orderId,
        BigDecimal total) {}

@Service
public class OrderEventPublisher {
    private static final Logger log =
            LoggerFactory.getLogger(OrderEventPublisher.class);

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        CompletableFuture<SendResult<String, OrderCreated>> future =
                kafkaTemplate.send("orders", event.orderId(), event);

        future.whenComplete((result, exception) -> {
            if (exception != null) {
                log.error("Publish failed, eventId={}", event.eventId(), exception);
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();
            log.info("Published eventId={} to topic={}, partition={}, offset={}",
                    event.eventId(), metadata.topic(), metadata.partition(),
                    metadata.offset());
        });

        return future;
    }
}
```

The `publish()` method returns the Kafka send future itself to the caller. The callback only logs and does not wait on additional work. As a result, the caller can still observe the outcome or compose the future with other tasks.

`whenComplete()` returns a new future. The new future preserves the original outcome if the callback runs normally; if the callback itself throws an exception, the new future can complete exceptionally. Therefore, if callback logic might fail and the callback outcome matters, retain the returned future or handle exceptions inside the callback.

## 5. Reading metadata after a successful send

`SendResult` is only available when sending succeeds. You can use `thenApply()` to map the send result into a more concise receipt object.

```java
public record PublishReceipt(
        String topic,
        int partition,
        long offset,
        long timestamp) {}

public CompletableFuture<PublishReceipt> publishWithReceipt(
        OrderCreated event) {
    return kafkaTemplate.send("orders", event.orderId(), event)
            .thenApply(sendResult -> {
                RecordMetadata metadata = sendResult.getRecordMetadata();
                return new PublishReceipt(
                        metadata.topic(),
                        metadata.partition(),
                        metadata.offset(),
                        metadata.timestamp());
            });
}
```

`thenApply()` runs only if the preceding future completed normally. If sending fails, the error propagates to the resulting future and the mapping function is skipped. This allows the service to expose only needed details instead of coupling upstream layers directly to `SendResult`.

## 6. Distinguishing CompletableFuture composition methods

`CompletableFuture` offers several chaining methods to handle success, failure, or both:

| Method | When does it run? | Result |
|---|---|---|
| `thenApply(fn)` | When the previous future succeeds | Transforms the value into a new value |
| `thenAccept(consumer)` | When the previous future succeeds | Consumes the result without returning a business value (`Void`) |
| `thenRun(action)` | When the previous future succeeds | Runs an action without receiving the result |
| `thenCompose(fn)` | When the previous future succeeds and the function returns another future | Chains two asynchronous operations without nested futures |
| `whenComplete(action)` | When the future succeeds or fails | Observes result/error and preserves the outcome if the callback does not throw |
| `handle(fn)` | When the future succeeds or fails | Transforms both result and error into a new outcome |
| `exceptionally(fn)` | When the future fails | Converts an error into a fallback value if recoverable |

Example chaining two asynchronous operations:

```java
CompletableFuture<PublishReceipt> receiptFuture =
        kafkaTemplate.send("orders", event.orderId(), event)
                .thenApply(sendResult -> {
                    RecordMetadata metadata = sendResult.getRecordMetadata();
                    return new PublishReceipt(
                            metadata.topic(), metadata.partition(),
                            metadata.offset(), metadata.timestamp());
                });

CompletableFuture<AuditResult> auditFuture = receiptFuture
        .thenCompose(auditService::recordPublishReceipt);
```

Assuming `recordPublishReceipt()` returns `CompletableFuture<AuditResult>`, `thenCompose()` flattens the audit future onto the chain. Using `thenApply()` here would produce `CompletableFuture<CompletableFuture<AuditResult>>`, forcing the caller to deal with nested futures.

## 7. Handling errors from the future

When the producer fails to send a record, the future can complete exceptionally. Causes include serialization errors, connection errors, timeouts, broker write rejections, missing permissions, or unsatisfied ISR conditions. Some errors raised while preparing the send call can be thrown directly from `send()` before the caller even receives a future; for complete handling, wrap both the `send()` call and future observation in appropriate exception handling.

You can handle errors with `exceptionally()`:

```java
CompletableFuture<PublishReceipt> receiptFuture =
        kafkaTemplate.send("orders", event.orderId(), event)
                .thenApply(sendResult -> {
                    RecordMetadata metadata = sendResult.getRecordMetadata();
                    return new PublishReceipt(
                            metadata.topic(), metadata.partition(),
                            metadata.offset(), metadata.timestamp());
                })
                .exceptionally(exception -> {
                    log.error("Cannot publish eventId={}",
                            event.eventId(), exception);
                    throw new CompletionException(exception);
                });
```

In this example, the exception is logged and rethrown wrapped in `CompletionException`, so the future still fails. Returning a default receipt instead would turn the future into a success; only do that if the business layer genuinely accepts a fallback value.

When both success and failure branches need to be unified into a single result type, use `handle()`:

```java
public record PublishOutcome(
        boolean published,
        PublishReceipt receipt,
        String errorMessage) {}

CompletableFuture<PublishOutcome> outcomeFuture =
        kafkaTemplate.send("orders", event.orderId(), event)
                .handle((sendResult, exception) -> {
                    if (exception != null) {
                        return new PublishOutcome(
                                false, null, exception.getMessage());
                    }

                    RecordMetadata metadata = sendResult.getRecordMetadata();
                    PublishReceipt receipt = new PublishReceipt(
                            metadata.topic(), metadata.partition(),
                            metadata.offset(), metadata.timestamp());
                    return new PublishOutcome(true, receipt, null);
                });
```

`handle()` turns errors into business data. This is handy when callers want an explicit status object, but avoid treating `published=false` as a successful send. The system must still record the failure and decide whether to retry, persist it, or report an error to the caller.

### Unwrapping exceptions

When using `get()`, errors are typically wrapped in `ExecutionException`; with `join()` and certain `CompletableFuture` stages, errors are typically wrapped in `CompletionException`. You can walk `getCause()` to inspect the root cause:

```java
Throwable cause = exception;
while ((cause instanceof CompletionException
        || cause instanceof ExecutionException)
        && cause.getCause() != null) {
    cause = cause.getCause();
}

log.error("Kafka publish root cause", cause);
```

In practice, classify errors by Kafka/Spring Kafka exception type and send context. Do not parse exception message strings alone, as message text can change across versions.

## 8. Which thread runs the callback?

Stages without the `Async` suffix, such as `thenApply()`, `thenAccept()`, or `whenComplete()`, can execute on the thread that completes the future. For the Kafka producer, send-acknowledgement callbacks are typically invoked from the producer's I/O thread; consequently, logic attached to the future can run on a thread critical to sending throughput.

Do not perform the following inside non-async callbacks:

- Blocking HTTP or database calls that may wait a long time.
- Waiting on another future via `get()` or `join()`.
- Heavy computations or large batch processing.
- Calling back into Kafka in a way that creates mutual waiting chains.

If heavy work is needed, use an `*Async` stage with a managed executor:

```java
CompletableFuture<PublishReceipt> receiptFuture =
        kafkaTemplate.send("orders", event.orderId(), event)
                .thenApplyAsync(sendResult -> {
                    RecordMetadata metadata = sendResult.getRecordMetadata();
                    return new PublishReceipt(
                            metadata.topic(), metadata.partition(),
                            metadata.offset(), metadata.timestamp());
                }, publishExecutor);
```

`publishExecutor` should be a bounded-thread/bounded-queue executor whose lifecycle is managed by Spring. Without an explicit executor, `*Async()` stages normally use `ForkJoinPool.commonPool()`, which is not always suitable for application workloads.

## 9. Waiting on one future or multiple futures

If the caller must wait for the result, you can use `get(timeout, unit)` or `join()`. Both block the calling thread; they do not change the asynchronous nature of the Kafka producer.

```java
SendResult<String, OrderCreated> result =
        kafkaTemplate.send("orders", event.orderId(), event)
                .get(5, TimeUnit.SECONDS);
```

With `get()`, handle `InterruptedException`, `ExecutionException`, and `TimeoutException`. If a timeout occurs, the send outcome may be uncertain: the request might still be in flight within the producer and the future might complete later. Never assume a timeout proves the record never reached the broker.

When sending multiple records, `CompletableFuture.allOf()` waits for all futures to finish:

```java
List<CompletableFuture<SendResult<String, OrderCreated>>> futures =
        events.stream()
                .map(event -> kafkaTemplate.send(
                        "orders", event.orderId(), event))
                .toList();

CompletableFuture<Void> all =
        CompletableFuture.allOf(futures.toArray(CompletableFuture[]::new));

all.whenComplete((ignored, exception) -> {
    if (exception != null) {
        log.error("At least one event could not be published", exception);
        return;
    }

    log.info("All {} events were acknowledged by Kafka", futures.size());
});
```

`allOf()` only creates a composite `Void` future; it does not return a list of `SendResult`s. If one component future fails, the composite future also fails. Other records might still have succeeded, so do not blindly retry the entire batch. Track each individual future and event ID to know which records need follow-up.

## 10. Timeouts, cancellation, and uncertain states

Distinguish three situations:

| Situation | Meaning |
|---|---|
| Future completes normally | Producer received acknowledgement per configured `acks` |
| Future completes exceptionally | Producer failed to complete the send; inspect the cause |
| Caller times out waiting | Caller stopped waiting; the send may still be in progress or its outcome unknown |

`future.cancel(true)` affects the `CompletableFuture` state, but do not assume it can recall a record already handed to the Kafka producer or reliably abort an active network request. If a business task needs cancellation, design state and idempotency at the application layer; do not rely on `cancel` to prove Kafka never received the record.

When retrying after a timeout, use a stable `eventId` and design idempotent consumers. Re-sending the same event can cause the consumer to receive two identical records even with producer idempotence enabled, because an idempotent producer primarily protects internal retries within a single producer session under Kafka's guarantees rather than deduplicating fresh application `send()` calls.

## 11. CompletableFuture is not business-processing confirmation

The future from `KafkaTemplate.send()` represents the outcome of writing the record to Kafka. When the future succeeds, it does not mean:

- The consumer has polled the record.
- The listener has finished business processing.
- The consumer's database has committed.
- Downstream emails, payments, or APIs have completed.

If you need confirmation that a consumer processed the event, design a dedicated feedback mechanism such as a result event, request-reply over Kafka, or persisted business state. Do not interpret `SendResult` as a receipt confirming the entire workflow.

If writing business data to a database and emitting an event must stay consistent, consider Transactional Outbox. `CompletableFuture` only observes asynchronous send results; it does not create a distributed transaction across the database and Kafka.

## 12. Testing futures from send operations

Tests should verify the return type, success path, failure path, and threading behavior:

1. **Return type:** confirm `KafkaTemplate.send()` returns `CompletableFuture<SendResult<K, V>>` for your project's Spring Kafka version.
2. **Success:** send a record to a test broker, await the future, and check topic, partition, and offset in `SendResult`.
3. **Callback:** confirm `whenComplete()` receives the result on success and the exception on error.
4. **Composition:** verify `thenApply()` transforms metadata and `thenCompose()` chains the second future properly.
5. **Exceptions:** make the broker unavailable or misconfigured to confirm the future completes exceptionally and the root cause is recorded.
6. **Timeouts:** simulate a slow response and confirm the caller does not treat a timeout as proof the record was not written.
7. **Multiple records:** test `allOf()` and per-future status when only part of a batch fails.
8. **Threading:** verify heavy callbacks are offloaded to an appropriate executor instead of blocking the producer's I/O thread.

You can use `spring-kafka-test` or the Kafka test starter matching your Spring Boot version. For realistic network errors, broker failovers, and timeouts, supplement with tests against a broker/container close to the deployment environment.

## 13. Summary

- `KafkaTemplate.send()` returns `CompletableFuture<SendResult<K, V>>` in Spring Kafka 3.0+.
- `SendResult` holds `ProducerRecord` and `RecordMetadata`, identifying the topic, partition, and offset acknowledged by the broker.
- `whenComplete()` observes both success and failure; `thenApply()` transforms the result; `thenCompose()` chains another future.
- `exceptionally()` and `handle()` help process errors, but must not mask failures as fake successes.
- Non-async callbacks can run on the thread completing the future; keep callbacks brief and offload heavy work to an executor.
- Timeouts or cancellation do not prove a record was not sent; retries need stable event IDs and idempotency.
- The future confirms the Kafka write outcome, not that a consumer completed business processing.

By understanding `CompletableFuture` and `SendResult`, you can build non-blocking Spring Kafka producers, observe send failures, and propagate asynchronous outcomes cleanly across service layers.
