# Synchronous and Asynchronous Sending

## 1. How the Kafka producer sends records

In Spring Kafka, `KafkaTemplate` is the commonly used API for sending records to Kafka. When `send()` is called, the application passes the topic, key, and value (along with optional metadata) to the Kafka producer. The producer serializes the data into bytes, places the record into its send buffer, and hands off transmission to the broker to a background I/O thread.

What must be distinguished is **how the producer sends** and **how the application waits for the result**. The Kafka producer sends asynchronously by design. `KafkaTemplate.send()` returns a `CompletableFuture<SendResult<K, V>>` in modern Spring Kafka. The application can continue working and receive the result via a callback, or wait for the future to complete to achieve synchronous behavior on the calling thread.

```text
Business service
      |
      | KafkaTemplate.send(topic, key, value)
      v
KafkaTemplate / ProducerFactory
      |
      v
KafkaProducer ── serialize ── producer buffer
      |                              |
      | returns CompletableFuture    | background sender I/O
      v                              v
Calling thread continues       Kafka broker
                                     |
                                     v
                              broker acknowledgement
                                     |
                                     v
                              completes future
```

The future completes successfully when the producer receives an acknowledgement according to its `acks` configuration (or the chosen acknowledgement mode). This indicates that the broker processed the write request at the corresponding acknowledgement level; it does **not** prove that a consumer has received or finished processing the event.

## 2. Asynchronous sending with KafkaTemplate

Asynchronous sending is the natural way to use `KafkaTemplate.send()`: call the method, receive the future, and do not block the current thread waiting for broker acknowledgement. The application can return the future to the caller layer or register a callback to handle the result.

### Publisher example

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
                log.error("Cannot publish event {}", event.eventId(), exception);
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();
            log.info("Published event {} to {}-{} at offset {}",
                    event.eventId(), metadata.topic(), metadata.partition(),
                    metadata.offset());
        });

        return future;
    }
}
```

In this example:

- `KafkaTemplate.send()` returns the future right after the producer accepts the send request and prepares to send the record.
- `whenComplete()` registers an action when the future completes, whether it succeeds or fails.
- On success, `SendResult` provides `RecordMetadata` such as topic, partition, and offset.
- On failure, the callback receives the exception to log, update state, or trigger appropriate handling.
- The method returns the future to the caller layer so that layer can track the result instead of losing send information.

A callback should not perform heavy work or wait on another task. It may run on the thread completing the send operation; if the callback blocks for a long time, it can affect the processing of other callbacks. Keep callbacks short, or offload heavy work to an explicitly managed executor.

### Handling results with CompletableFuture

Besides `whenComplete()`, you can use `CompletableFuture` transformations:

```java
CompletableFuture<String> result =
        kafkaTemplate.send("orders", event.orderId(), event)
                .thenApply(sendResult -> {
                    RecordMetadata metadata = sendResult.getRecordMetadata();
                    return metadata.topic() + "-" + metadata.partition()
                            + "-" + metadata.offset();
                });
```

`thenApply()` transforms the result into a new value. `thenAccept()` is used when you only need to consume the result; `whenComplete()` fits when you want to observe the result while preserving the original completion value. `exceptionally()` can turn an error into a fallback result, though caution is needed: returning a default value without recording the error may hide send failures.

In Spring Kafka 3.x and later, the send API returns `CompletableFuture`. Older Spring Kafka 2.x versions use `ListenableFuture`; when working with legacy projects, match the return type of the version in use rather than copying newer examples into older codebases.

## 3. Synchronous sending by waiting on the future

Although `send()` is asynchronous, the application can wait for the result using `get()` or `join()`. Doing so blocks the calling thread until the producer receives an acknowledgement or the operation fails.

### Using get() with a timeout

```java
public SendResult<String, OrderCreated> publishAndWait(
        OrderCreated event) {
    try {
        return kafkaTemplate.send("orders", event.orderId(), event)
                .get(10, TimeUnit.SECONDS);
    } catch (InterruptedException exception) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException(
                "Interrupted while waiting for Kafka acknowledgement",
                exception);
    } catch (ExecutionException exception) {
        throw new IllegalStateException(
                "Kafka rejected or failed to send the event",
                exception.getCause());
    } catch (TimeoutException exception) {
        throw new IllegalStateException(
                "Timed out waiting for Kafka acknowledgement; outcome may be unknown",
                exception);
    }
}
```

`get(10, TimeUnit.SECONDS)` blocks the calling thread for at most 10 seconds. If the broker acknowledges sooner, the method returns `SendResult`; if sending fails, `ExecutionException` holds the cause; if the wait time expires, `TimeoutException` is thrown.

When catching `InterruptedException`, restore the interrupt flag with `Thread.currentThread().interrupt()` so the thread-management layer can recognize the stop signal.

**Timing out while waiting does not mean the record was definitely not sent.** The future may still complete after `get()` throws `TimeoutException`, because the send request is still being processed by the producer. If the caller immediately resends the same event, the broker may receive it twice. Use a stable event ID, idempotent handling, and a controlled retry policy to avoid duplicate side effects.

### Using join()

```java
SendResult<String, OrderCreated> result =
        kafkaTemplate.send("orders", event.orderId(), event).join();
```

`join()` also blocks the calling thread until the future completes, but does not accept a timeout directly and typically wraps failures in `CompletionException`. For request handling that needs a time bound, `get(timeout, unit)` is usually easier to control. Do not call `join()` on an event loop or a request-serving thread with strict latency requirements without evaluating thread-blocking risk.

## 4. Comparing synchronous and asynchronous sending

| Criterion | Asynchronous sending | Synchronous waiting |
|---|---|---|
| Invocation | Call `send()` and continue; handle result via future/callback | Call `send().get()` or `send().join()` |
| Calling thread | Does not wait for broker acknowledgement | Blocked until result or timeout |
| Throughput | Can have multiple in-flight records simultaneously, leveraging producer batching | May reduce throughput if waiting sequentially for each record |
| Error handling | Handled via future callback or by passing the future to the caller | Caught immediately at the wait site |
| Best suited for | Event flows that can continue and track results later | Needing the broker result before returning a business response or taking the next step |
| Primary risk | Forgetting the future leaves send errors unobserved; callbacks blocking threads | Blocking threads, increasing latency, and causing bottlenecks if overused |

Asynchronous sending does not mean "fire and forget." If an event is important, the application must observe the future and decide how to handle errors. Synchronous sending also does not guarantee immediate consumer processing; it only waits for write acknowledgement from the Kafka broker.

## 5. Producer configuration related to send acknowledgements

The application-layer waiting strategy needs to align with producer configuration. A commonly used configuration for important business events:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
```

- `acks=all` instructs the leader to wait for currently available replicas in the ISR to acknowledge per the replication protocol before returning success.
- `enable.idempotence=true` helps the producer avoid duplicate records caused by internal producer retries within Kafka's guarantees.
- `delivery.timeout.ms` bounds the total time the producer tries to complete sending a record, including acknowledgement waiting and retries per client configuration.

`acks=all` does not automatically mean every replica per the replication factor acknowledges if a replica is not in the ISR. You can combine it with `min.insync.replicas` at the topic/broker level to require a minimum number of replicas in the ISR when writing. Producer and broker settings must be designed together.

In addition, `max.block.ms` can cause the `send()` call itself to block while waiting for metadata or waiting for space in the producer buffer. Therefore, an API returning a future does not mean every code path of the call is strictly non-blocking. Configure timeouts and monitor latency according to real workloads.

## 6. Handling errors when sending asynchronously

Send failures can occur at several stages:

- Configuration or data serialization errors before the record is sent.
- Unavailable broker, network errors, or timeouts.
- Broker write rejections due to authorization, topic, or ISR conditions.
- Producer delivery timeout expiring after retries.

When the future completes exceptionally, the application should classify the error. Transient errors can be retried according to policy; configuration errors or invalid data require fixing the root cause. Do not retry infinitely or treat all exceptions identically.

Example of handling errors in a callback:

```java
CompletableFuture<SendResult<String, OrderCreated>> future =
        kafkaTemplate.send("orders", event.orderId(), event);

future.whenComplete((result, exception) -> {
    if (exception != null) {
        Throwable cause = exception.getCause() != null
                ? exception.getCause() : exception;
        log.error("Publish failed for eventId={}", event.eventId(), cause);
        // Record failure state or route into a controlled retry workflow.
        return;
    }

    log.info("Publish confirmed: topic={}, partition={}, offset={}",
            result.getRecordMetadata().topic(),
            result.getRecordMetadata().partition(),
            result.getRecordMetadata().offset());
});
```

If the callback merely logs the error and drops it, the business layer may not know the event failed. For events that must be emitted reliably, persist send state, use a Transactional Outbox, or implement a durable retry mechanism aligned with the system's transaction boundaries.

Do not call `future.get()` right after `send()` inside code claimed to be "asynchronous"; doing so makes the calling thread synchronous. Likewise, do not call `CompletableFuture.runAsync(() -> kafkaTemplate.send(...))` just to make Kafka send asynchronously, because the Kafka producer already sends on a background I/O thread and wrapping it in another executor adds no delivery guarantees.

## 7. Sending multiple records and batching

The Kafka producer can group multiple records into batches per partition to reduce network requests. Asynchronous sending lets the application place multiple records into the producer buffer before awaiting results, giving the producer a better opportunity to batch.

Properties that commonly affect batching:

- `batch.size`: target batch size per partition.
- `linger.ms`: time the producer may wait for additional records to form a larger batch.
- `buffer.memory`: producer buffer capacity.
- `max.in.flight.requests.per.connection`: number of unacknowledged requests per connection.

Configuration example:

```yaml
spring:
  kafka:
    producer:
      properties:
        batch.size: 32768
        linger.ms: 5
        buffer.memory: 67108864
```

The values above are illustrative examples only, not a universal optimal configuration. Larger batches or higher `linger.ms` can improve throughput but also increase latency and memory usage. Measure against real record sizes, partition counts, traffic, and SLAs.

If you call `send().get()` sequentially after each record, the application generally fails to leverage batching well because it always waits for acknowledgement before sending the next record. When sending multiple records, you can submit the futures first and then wait for all of them to finish:

```java
List<CompletableFuture<SendResult<String, OrderCreated>>> futures =
        events.stream()
                .map(event -> kafkaTemplate.send(
                        "orders", event.orderId(), event))
                .toList();

CompletableFuture<Void> allSends =
        CompletableFuture.allOf(futures.toArray(CompletableFuture[]::new));

allSends.join(); // Completes successfully only if all futures succeed.
```

In production, handle `allOf` exceptions, inspect each individual future to know which records succeeded or failed, and avoid blindly retrying the entire batch. `allOf()` does not itself return the list of results; read each future after the group completes.

## 8. Ordering in synchronous and asynchronous sending

Kafka guarantees record order within a single partition. Producers sending records with the same key typically route to the same partition according to the configured partitioner. However, sending asynchronously from multiple threads can cause requests to enter the producer in a race order between threads.

If business logic requires per-entity ordering:

- Use a stable key such as `orderId` so events for the same order go to the same partition.
- Avoid sending events for the same entity in parallel from multiple threads when call order is uncontrolled.
- Enable the idempotent producer and keep compatible producer settings so retries do not invert order within Kafka's guarantees.
- If a strict event sequence is needed, establish emission ordering in the business service and test under retries, timeouts, and rebalances.

Sending synchronously record-by-record on a single thread simplifies the sequence of awaiting acknowledgements, but does not create global ordering across partitions. Conversely, asynchronous sending does not inherently break ordering if records are sent to the same partition in the right order; what must be controlled is emission order and concurrency.

## 9. Sending events in business flows

When an order is created, the Order Service may emit `OrderCreated` and must decide when to return a response to its calling API.

**Wait for Kafka acknowledgement before returning:** suitable when the API is only considered complete after the broker confirms the record write. This makes the request wait on Kafka and requires an appropriate timeout. On timeout, the send outcome may be unknown; an event ID and safe retry handling are required.

**Return first, track sending asynchronously:** can reduce request wait time, but requires the application to track errors and ensure events are not lost if the process stops. Creating a future and forgetting it is not a reliable delivery strategy.

If saving the order to the database and publishing the event must be atomic, calling `KafkaTemplate.send()` after committing the database still leaves a gap: the database may have committed, yet the application crashes before Kafka receives the event. For this case, consider the Transactional Outbox pattern: write the order and an outbox record in the same database transaction, then have a separate publisher send outbox records to Kafka and mark them sent.

## 10. Testing synchronous and asynchronous sending

Tests should verify both send outcomes and calling-thread behavior:

1. **Successful send:** send a record to a test broker, wait for the future to complete, and verify topic, partition, and offset in `SendResult`.
2. **Not blocking the calling thread:** invoke the asynchronous publisher and confirm the method returns the future before the callback completes under controlled test conditions.
3. **Send failure:** use a stopped broker or invalid configuration to confirm the future completes exceptionally and errors are recorded.
4. **Timeout:** bound the wait time in the caller layer and verify the system does not assume the record was definitely not written.
5. **Multiple records:** send a group of records, inspect all futures, and verify partial batch failures are not missed.
6. **Ordering:** send events with the same key, confirm they land in the same partition, and are read in append order.
7. **Application shutdown:** test how the application handles pending futures on shutdown and whether there is a mechanism to persist unsent events.

You can use `spring-kafka-test` or the Kafka test starter matching your Spring Boot line for integration testing. For network timeouts, broker failovers, and heavy load, supplement with tests using a Kafka broker/container close to the deployment environment.

## 11. Choosing a strategy in Spring Kafka applications

| Situation | Appropriate approach |
|---|---|
| Send one event and need broker confirmation before continuing | `kafkaTemplate.send(...).get(timeout, unit)` |
| Send an event and let the caller decide when to wait | Return `CompletableFuture<SendResult<K, V>>` |
| Log or update metrics when sending completes | `whenComplete()` with a short callback |
| Transform send metadata into another result | `thenApply()` or `thenCompose()` |
| Send multiple records to leverage batching | Issue multiple `send()` calls first, then track futures or `allOf()` |
| Event must be emitted durably alongside a database business transaction | Transactional Outbox with a retrying publisher |

For most producers in Spring Kafka, keep the API asynchronous and let the caller layer decide whether it needs to wait for the result. When waiting is required, set a finite timeout, distinguish timeouts from confirmation failures, and design retries by event ID to avoid creating duplicate business records.

## 12. Summary

- `KafkaTemplate.send()` sends asynchronously and returns `CompletableFuture<SendResult<K, V>>` in modern Spring Kafka.
- Calling `get()` or `join()` makes the calling thread wait for the result, creating synchronous usage on the application side.
- `whenComplete()`, `thenApply()`, and future transformations process results without blocking the calling thread.
- Future success reflects write acknowledgement per producer configuration, not proof that consumers have processed the event.
- Waiting timeout does not prove the record was not sent; retries require an event ID and idempotency.
- `acks`, idempotence, delivery timeout, batching, and partition keys affect reliability, latency, and ordering.
- For critical events, observe failures and consider an Outbox to avoid losing events between the database and Kafka.

Understanding the difference between asynchronous sending and synchronous waiting helps design producers aligned with application SLAs. `KafkaTemplate` provides the background sending mechanism; the application decides how to wait, handle errors, and ensure events are emitted reliably.
