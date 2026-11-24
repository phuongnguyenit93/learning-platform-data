# send Callbacks and CompletableFuture

In Spring Kafka, sending a record is an asynchronous operation. The application calls `KafkaTemplate` to hand the record to the Kafka producer; the producer serializes it, selects a partition, adds it to a batch, and sends it to the broker on a background thread. The send outcome can succeed or fail after the `send()` method has already returned.

Starting in Spring Kafka 3.0, `KafkaTemplate`'s `send()` methods return `CompletableFuture<SendResult<K, V>>`. The future lets the application register callbacks, chain asynchronous processing steps, and propagate errors to callers without blocking a thread merely to wait for the broker's response. The material below focuses on Spring Kafka 3.x and later; the end notes differences with older versions using `ListenableFuture`.

## 1. What Does send() Actually Confirm?

Calling `send()` does not mean the record has been written to Kafka. It initiates the send process and returns a future representing the outcome. Once the producer finishes the operation per the acknowledgement configuration, the future completes:

- If the broker acknowledges per the `acks` policy, the future completes normally with a `SendResult`.
- If sending fails, delivery times out, or the producer encounters an error, the future completes exceptionally with an exception.
- Some errors—such as an uninitialized producer, an unserializable record, or invalid arguments—can occur immediately inside the `send()` call before the application receives a future. Therefore, the `send()` call site still needs synchronous error handling.

The success milestone depends on producer configuration. With `acks=all`, the broker leader only acknowledges after replicas currently in the ISR satisfy write conditions. With `acks=1`, only leader confirmation is required. With `acks=0`, the producer does not wait for broker ACKs, so the future does not carry the same durability confirmation semantics as the other two modes.

Even when the future succeeds, that only indicates the producer finished sending according to the `acks` policy. It does not prove a consumer read the record, a listener ran, or a business database committed. Producer acknowledgement and consumer processing acknowledgement are two distinct boundaries.

Typical send flow:

    Application
       |
       | KafkaTemplate.send(record)
       v
    KafkaTemplate / KafkaProducer
       |
       | serialize, partition, batch
       v
    Broker leader ----> ISR replicas
       |
       | ACK or error
       v
    CompletableFuture completes
       |
       +---- success: SendResult
       |
       +---- failure: exception

## 2. CompletableFuture and SendResult

`CompletableFuture` is an object representing a result that may arrive in the future. Right after calling `send()`, the application can continue doing other work. When the send operation finishes, registered callbacks or dependent stages are triggered.

In Spring Kafka 3.x, the typical return type is:

~~~java
CompletableFuture<SendResult<String, OrderCreated>> future =
        kafkaTemplate.send("orders.created", orderId, event);
~~~

The two generic types in the example represent the record's key and value types. `SendResult` holds the sent `ProducerRecord` and the `RecordMetadata` returned by the broker.

Metadata fields useful for logging and tracking:

- topic: destination topic.
- partition: partition that received the record.
- offset: position of the record within the partition.
- timestamp: timestamp recorded by the broker per topic timestamp mode.
- serialized key/value size: size of serialized data, if provided by metadata.

Example reading metadata:

~~~java
SendResult<String, OrderCreated> result = future.join();
RecordMetadata metadata = result.getRecordMetadata();

String topic = metadata.topic();
int partition = metadata.partition();
long offset = metadata.offset();
~~~

The snippet above uses `join()` to illustrate retrieving results after the future finishes. In normal asynchronous flows, use callbacks instead of calling `join()` immediately after `send()`, because `join()` blocks the current thread until a result arrives.

## 3. Registering Callbacks with whenComplete()

`whenComplete()` is the direct way to observe both outcomes: success and failure. The callback receives two parameters:

- result: `SendResult` if the operation completed normally.
- exception: exception if the future completed exceptionally; on success, this value is `null`.

Example:

~~~java
CompletableFuture<SendResult<String, OrderCreated>> future =
        kafkaTemplate.send("orders.created", orderId, event);

future.whenComplete((result, exception) -> {
    if (exception != null) {
        log.error("Cannot publish eventId={}", event.eventId(), exception);
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();

    log.info(
        "Published eventId={} topic={} partition={} offset={}",
        event.eventId(),
        metadata.topic(),
        metadata.partition(),
        metadata.offset()
    );
});
~~~

The success callback should only record the send outcome and needed metadata. The failure callback should log `eventId`, topic, key, and cause for investigation. Do not log full sensitive payloads.

`whenComplete()` returns a new `CompletableFuture` representing the callback stage. If the callback finishes normally, the stage preserves the source future's success or failure outcome. If the callback itself throws an exception, the dependent stage can also fail. When a callback only logs or increments metrics, avoid letting auxiliary operations throw exceptions that alter how callers observe the result.

If the caller still needs the send status, retain and return the original future or deliberately return the dependent stage. Do not attach a callback and discard all error propagation paths when the application needs to know publishing failed.

## 4. Handling Synchronous and Asynchronous Errors

There are two moments where exceptions must be handled.

**Synchronous errors** occur immediately during the `send()` call. Examples include a producer not ready, an unserializable record, or invalid input arguments. Since no future was returned yet, callbacks cannot handle these errors.

**Asynchronous errors** occur after `send()` returns the future. Examples include a broker unable to serve the request, request timeouts, or dropped connections. These errors complete the future exceptionally and are delivered to callbacks.

You can combine `try/catch` with `whenComplete()`:

~~~java
public CompletableFuture<SendResult<String, OrderCreated>> publish(
        OrderCreated event) {

    try {
        CompletableFuture<SendResult<String, OrderCreated>> future =
                kafkaTemplate.send("orders.created", event.orderId(), event);

        future.whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                    "Publish failed eventId={}",
                    event.eventId(),
                    exception
                );
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();

            log.info(
                "Publish succeeded eventId={} partition={} offset={}",
                event.eventId(),
                metadata.partition(),
                metadata.offset()
            );
        });

        return future;
    }
    catch (RuntimeException exception) {
        log.error(
            "Publish could not be started eventId={}",
            event.eventId(),
            exception
        );

        CompletableFuture<SendResult<String, OrderCreated>> failed =
                new CompletableFuture<>();

        failed.completeExceptionally(exception);
        return failed;
    }
}
~~~

The method above returns a future to the caller. If an error occurs while initiating the send, it returns an exceptionally completed future to unify how results are observed. The caller must still handle a failed future; logging inside a callback does not replace business error handling.

Do not merely catch the exception and return `null`. Doing so prevents the caller from distinguishing a failed publish, an unstarted publish, or a valid result value.

## 5. Commonly Used Stage-Chaining Methods

`CompletableFuture` provides multiple methods to chain processing steps. Each serves a distinct purpose.

| Method | Purpose | When appropriate |
|---|---|---|
| whenComplete | Observe success or failure and preserve completion state | Logging, metrics, tracing |
| thenApply | Transform the result into another value | Extracting `RecordMetadata` or mapping `SendResult` |
| thenAccept | Consume the result to perform an action, returning no value | Recording metrics or updating a counter |
| thenRun | Run an action after the stage succeeds, without needing the result | Executing an independent post-publish step |
| exceptionally | Recover when a stage fails by supplying a fallback value | Use only when there is a clear recovery strategy |
| handle | Process both result and exception, producing a new result | Normalizing success/failure states |
| thenCompose | Chain another asynchronous operation and flatten nested futures | Sending a follow-up event or calling an async service |

### 5.1. thenApply and thenAccept

Use `thenApply` when converting `SendResult` into metadata or another value:

~~~java
CompletableFuture<RecordMetadata> metadataFuture =
        kafkaTemplate.send("orders.created", event.orderId(), event)
                .thenApply(SendResult::getRecordMetadata);
~~~

Use `thenAccept` when only consuming the result to perform an action:

~~~java
CompletableFuture<Void> logFuture =
        kafkaTemplate.send("orders.created", event.orderId(), event)
                .thenAccept(result -> {
                    RecordMetadata metadata = result.getRecordMetadata();
                    log.info(
                        "Published to {}-{} at offset {}",
                        metadata.topic(),
                        metadata.partition(),
                        metadata.offset()
                    );
                });
~~~

If the prior stage fails, `thenApply` and `thenAccept` skip their success handlers; the error propagates forward to the new stage. Therefore, place error-handling branches at the right position in the chain.

### 5.2. exceptionally and the Risk of Swallowing Errors

`exceptionally()` runs when the prior stage fails. It can supply a fallback value to recover the stage:

~~~java
CompletableFuture<SendResult<String, OrderCreated>> recovered =
        kafkaTemplate.send("orders.created", event.orderId(), event)
                .exceptionally(exception -> {
                    log.error("Publish failed", exception);
                    return null;
                });
~~~

The example above turns a failed future into a normally completed future holding `null`. If the caller only checks whether the future failed, it will mistakenly assume the publish succeeded normally. This is a common design mistake: logging an exception and returning `null` accidentally swallows the failure.

Use `exceptionally()` to recover only when a valid fallback exists and the caller understands what that value means. If recovery is not possible, rethrow the exception or return a failed future:

~~~java
CompletableFuture<SendResult<String, OrderCreated>> propagated =
        kafkaTemplate.send("orders.created", event.orderId(), event)
                .exceptionally(exception -> {
                    log.error("Publish failed", exception);
                    throw new CompletionException(exception);
                });
~~~

When the goal is purely observing errors, `whenComplete()` is usually clearer than `exceptionally()` because it does not actively turn an error into a success result.

### 5.3. handle to Normalize Results

`handle()` always runs when the source stage completes, whether it succeeded or failed. It fits when mapping both branches into a single business outcome type:

~~~java
CompletableFuture<PublishOutcome> outcomeFuture =
        kafkaTemplate.send("orders.created", event.orderId(), event)
                .handle((result, exception) -> {
                    if (exception != null) {
                        return PublishOutcome.failed(
                            event.eventId(),
                            exception.getMessage()
                        );
                    }

                    RecordMetadata metadata = result.getRecordMetadata();

                    return PublishOutcome.sent(
                        event.eventId(),
                        metadata.topic(),
                        metadata.partition(),
                        metadata.offset()
                    );
                });
~~~

`PublishOutcome` is an application-defined type, such as a record or class. Because `handle()` returns a normal result in both branches, callers must inspect the status inside `PublishOutcome` instead of only checking whether the future threw an exception.

### 5.4. thenCompose to Chain Multiple Asynchronous Operations

`thenCompose()` is useful when the next step also returns a `CompletableFuture`. For example, after sending the first event successfully, the application needs to send a follow-up event:

~~~java
CompletableFuture<SendResult<String, OrderCreated>> first =
        kafkaTemplate.send("orders.created", event.orderId(), event);

CompletableFuture<SendResult<String, OrderAudited>> chain =
        first.thenCompose(result ->
                kafkaTemplate.send(
                    "orders.audit",
                    event.orderId(),
                    OrderAudited.from(event)
                )
        );
~~~

This chain sends the audit event only after the first future completes normally. If the first send fails, `thenCompose()` does not run and the error propagates to `chain`.

The two sends are still two independent producer operations. If business rules require both records to be written together or neither written, chaining futures does not create an atomic transaction. Use a Kafka transaction when both records belong to the same transactional flow and require atomicity within Kafka.

## 6. Which Thread Runs Callbacks?

Methods without the `Async` suffix, such as `whenComplete()`, `thenApply()`, and `thenAccept()`, may run on the thread that completes the future. For Kafka producer sends, that is typically the producer's response-handling thread. If the future already completed before the callback is registered, the callback may execute immediately on the registering thread.

Therefore, do not perform heavy work inside default callbacks. Operations such as slow HTTP calls, database queries, large file processing, or waiting on another future can stall the response-handling thread and hurt message-sending throughput.

When time-consuming post-processing is needed, use an `Async` variant with a bounded `Executor`:

~~~java
future.whenCompleteAsync((result, exception) -> {
    if (exception != null) {
        failureHandler.record(event.eventId(), exception);
        return;
    }

    auditService.recordPublished(
        event.eventId(),
        result.getRecordMetadata().offset()
    );
}, callbackExecutor);
~~~

`callbackExecutor` should be managed as a bean or component with a clear lifecycle. Size threads and queues for real load; unbounded queues can grow memory endlessly if callbacks run slower than the send rate.

Do not default to `ForkJoinPool.commonPool()` for every background task. If callbacks invoke blocking services or require concurrency limits, a dedicated executor provides resource control and load isolation.

If an async callback fails, the stage returned by `whenCompleteAsync()` also fails. Retain that stage if the callback outcome is part of an observable workflow; if the callback only logs, ensure it does not throw unexpected exceptions.

## 7. Waiting for Results with get() and join()

`CompletableFuture` provides two common waiting methods:

- `get()` blocks the thread until a result arrives. It can throw `InterruptedException` or `ExecutionException`; the `get(timeout, unit)` overload also throws `TimeoutException`.
- `join()` also blocks the thread, but generally wraps asynchronous errors in `CompletionException` instead of `ExecutionException`.

Bounded wait example:

~~~java
try {
    SendResult<String, OrderCreated> result =
            kafkaTemplate.send("orders.created", event.orderId(), event)
                    .get(10, TimeUnit.SECONDS);

    log.info(
        "Published at offset {}",
        result.getRecordMetadata().offset()
    );
}
catch (InterruptedException exception) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Interrupted while waiting for Kafka", exception);
}
catch (ExecutionException | TimeoutException exception) {
    throw new IllegalStateException("Kafka publish did not complete successfully", exception);
}
~~~

Synchronous waiting can be useful in integration tests, command-line jobs, or a processing boundary forced to return an immediate outcome. On high-load request threads or listener threads, blocking on every send reduces concurrency and throughput. Prefer returning the future or chaining callbacks when the business flow allows asynchrony.

The timeout of `get(timeout, unit)` only limits how long the current thread waits for the result. It does not mean the producer canceled the request or that the broker definitely did not write the record. If the application times out and resends immediately, the first record may still be written by the broker afterward; thus, application-layer retries can create duplicates.

Do not use caller wait timeouts as a substitute for the Kafka producer's `delivery.timeout.ms`. `delivery.timeout.ms` is how long the producer attempts to deliver a record; `request.timeout.ms` governs waiting for a single request response. Set values to match SLAs and remember that a timeout does not prove the record was not written.

## 8. Configuring the Producer So Futures Have Operational Meaning

Callbacks only reflect outcomes under the producer's configuration. For flows needing durability, start from this configuration:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
~~~

Meaning:

- `acks=all` requires the leader to wait for replicas in the ISR per cluster write conditions.
- `enable.idempotence=true` helps the producer avoid duplicate writes from protocol-layer retries within the producer session.
- `delivery.timeout.ms` caps the total time the producer tries to send a record before failing.
- `request.timeout.ms` caps the response wait time for a single request.

Pair `acks=all` with appropriate replication factor and `min.insync.replicas` on the broker/topic. If the cluster lacks enough replicas in the ISR, sends may fail; futures will report errors for the application and monitoring system to handle. Do not lower the acknowledgement level merely to make more callbacks succeed if doing so weakens required data safety.

The Kafka client enforces compatibility constraints among idempotence, `acks`, `retries`, and in-flight requests per connection. Do not arbitrarily set values conflicting with idempotence requirements. Verify effective producer config and documentation for the exact Kafka client version used by Spring Kafka.

## 9. Retrying After a Future Fails

When a future fails, first classify the error and determine whether the record might have already been written by the broker.

Some errors indicate the request was explicitly rejected, such as missing permissions or a record exceeding size limits. Certain network or timeout errors have indeterminate state: the broker may have written the record while the ACK never reached the producer. If the application creates a fresh send for the same event, two records can appear.

An idempotent producer handles retries performed by the Kafka producer within the same producer session. It does not automatically deduplicate when the application issues a new `send()` call for the same event after an old future fails, nor does it replace consumer idempotency.

Before retrying at the application layer, consider:

1. Classify the exception and determine whether the error is likely transient.
2. Keep the event's `eventId` unchanged across all send attempts.
3. Use exponential backoff with jitter, and cap total retry attempts.
4. Do not retry data, authentication, or configuration errors endlessly.
5. Design idempotent consumers to safely handle cases where a record was written yet the send result never reached the application.
6. Record attempt counts, causes, and final status for investigation.

Do not retry directly inside the callback via recursive `send()` calls or unbounded loops. That pattern can trigger traffic spikes, hold many futures, and hide configuration errors. Delegate retries to a clearly bounded component or use Transactional Outbox when events must be emitted durably alongside database changes.

### 9.1. Outbox for Events Requiring Durable Emission

If an application updates a database and then sends to Kafka, a failure gap exists between the database commit and broker receipt. Callbacks only report the Kafka send outcome; they do not turn the two systems into a single transaction.

Transactional Outbox bridges this gap by writing business changes and an outbox record in the same database transaction. A relay reads the outbox and sends records to Kafka. If the relay stops after Kafka wrote the record but before marking the outbox row sent, the relay may resend after restarting. Hence, `eventId` must stay stable and consumers must be idempotent.

Callbacks from `KafkaTemplate` can tell the relay which sends were acknowledged so it can update outbox status. Still, updating outbox status must also handle database errors and potential relay resends.

## 10. Callbacks in Kafka Transactions

When using Kafka transactions, a send may be acknowledged by the broker at the record level before the transaction commits. Consumers configured with `isolation.level=read_committed` only see records belonging to committed transactions.

Thus, a successful send future does not mean the transaction containing that record has committed. Applications must track transaction completion—including commit or abort—according to how Spring Kafka manages transactions.

Conceptual example:

    Start Kafka transaction
       |
       v
    Send record A ----> send future completes
       |
       v
    Send record B ----> send future completes
       |
       v
    Commit transaction
       |
       +---- success: records become visible to read_committed consumers
       |
       +---- failure/abort: records are not treated as committed data

Do not use a successful send callback to mark an entire transactional workflow complete. Place business status updates after the transaction commits successfully or use transaction synchronization mechanisms matching your Spring Kafka setup.

A Kafka transaction can combine output records with consumer offsets inside one Kafka transaction. It does not automatically span databases, HTTP APIs, or emails. External side effects still require outbox, inbox, or separate idempotency mechanisms.

## 11. Complete Publisher Example

The following example shows a service emitting an event, registering callbacks to log metadata, and returning the future to the caller. It assumes `KafkaTemplate` is configured with the corresponding serializer for `OrderCreated`.

~~~java
@Service
public class OrderEventPublisher {

    private static final Logger log =
            LoggerFactory.getLogger(OrderEventPublisher.class);

    private static final String TOPIC = "orders.created";

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        ProducerRecord<String, OrderCreated> record =
                new ProducerRecord<>(TOPIC, event.orderId(), event);

        record.headers().add(
                "event-id",
                event.eventId().getBytes(StandardCharsets.UTF_8)
        );

        final CompletableFuture<SendResult<String, OrderCreated>> future;

        try {
            future = kafkaTemplate.send(record);
        }
        catch (RuntimeException exception) {
            log.error(
                "Could not start publish for eventId={}",
                event.eventId(),
                exception
            );

            CompletableFuture<SendResult<String, OrderCreated>> failed =
                    new CompletableFuture<>();

            failed.completeExceptionally(exception);
            return failed;
        }

        future.whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                    "Kafka send failed eventId={} topic={}",
                    event.eventId(),
                    TOPIC,
                    exception
                );
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();

            log.info(
                "Kafka send acknowledged eventId={} topic={} partition={} offset={}",
                event.eventId(),
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });

        return future;
    }
}
~~~

Key imports:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;
~~~

Callers can chain post-publish actions:

~~~java
publisher.publish(event)
        .thenAccept(result -> {
            RecordMetadata metadata = result.getRecordMetadata();
            metrics.recordPublishSuccess(metadata.topic());
        })
        .exceptionally(exception -> {
            metrics.recordPublishFailure();
            return null;
        });
~~~

In the caller snippet, `exceptionally()` turns the stage into a normal completion after recording the metric. If the caller needs to report an error to users or route the event to an outbox, do not swallow the error like this; propagate the exception or return a result type clearly indicating failure.

## 12. Testing and Observing Send Outcomes

In integration tests, you can wait on the future with a finite timeout to verify the producer received an ACK and inspect metadata:

~~~java
SendResult<String, OrderCreated> result =
        kafkaTemplate.send("orders.created", event.orderId(), event)
                .get(10, TimeUnit.SECONDS);

assertThat(result.getRecordMetadata().topic())
        .isEqualTo("orders.created");
~~~

This synchronous wait is suitable in tests. In production applications, do not copy this wait into every request or listener without a clear reason.

Monitor these signals:

- Count of successful and failed sends.
- Rate of exceptionally completed futures by exception class.
- Latency from calling `send()` until the future completes.
- Counts of timeouts, retries, and serialization errors.
- Record counts sent per topic and partition.
- Outbox events waiting to send or stuck failing for long periods.
- Discrepancies between events the application intended to emit and records acknowledged by the producer.

Logs and traces should include `eventId`, topic, key, partition, offset, and correlation ID when available. Do not use offset as a business event ID because an offset only locates a record within a single partition.

Callbacks are a convenient point to measure send duration and log metadata, yet are not proof a consumer processed the record. To observe end-to-end, add consumer-side metrics and reconcile with business outcomes.

## 13. Common Implementation Mistakes

| Practice | Problem | Fix |
|---|---|---|
| Calling `send()` and assuming it succeeded | The future may complete exceptionally later | Register callbacks or pass the future to the caller |
| Catching errors only inside `whenComplete()` | Synchronous errors before future creation bypass the callback | Wrap the `send()` call in `try/catch` |
| Calling `get()` or `join()` right after `send()` | Blocks threads and reduces throughput | Chain stages or process asynchronously |
| Calling blocking services inside default callbacks | Can stall producer response-handling threads | Use `whenCompleteAsync()` with a bounded executor |
| Using `exceptionally()` and returning `null` | Turns failures into normal completion results | Recover only when a valid fallback result exists |
| Retrying immediately on timeout | The first attempt may have already been written by the broker | Preserve `eventId` and design idempotent consumers |
| Treating a successful send future as consumer completion | Producer ACK is not consumer ACK | Track consumer processing and business outcomes separately |
| Treating a successful send future as Kafka transaction commit | The record may still belong to an uncommitted transaction | Track transaction completion |
| Ignoring errors inside callbacks | Leaves no trace for investigation | Log with `eventId` and emit metrics/alerts |
| Using an unbounded callback executor | Slow callbacks can grow queues without bound | Enforce thread, queue, and rejection limits |

## 14. Differences Between Spring Kafka 2.x and 3.x

Examples in this guide use the `CompletableFuture` API from Spring Kafka 3.0 onward. In older Spring Kafka versions, `KafkaTemplate.send()` returned `ListenableFuture<SendResult<K, V>>`. Applications registered callbacks using `addCallback()` instead of `whenComplete()`:

~~~java
ListenableFuture<SendResult<String, OrderCreated>> future =
        kafkaTemplate.send("orders.created", event.orderId(), event);

future.addCallback(
    result -> log.info("Publish succeeded"),
    exception -> log.error("Publish failed", exception)
);
~~~

When upgrading to Spring Kafka 3.x, the return type changes to `CompletableFuture`. Inspect imports, variable types, callbacks, and any code calling `addCallback()` during upgrades. You cannot call `whenComplete()` directly on an older version's `ListenableFuture` without migrating or adapting the API.

Configuration, transaction management, and supporting APIs also depend on Spring Kafka version. Always check your application's actual dependencies before applying examples.

## 15. Principles for Use in Production Systems

- Treat the future as the result of a send operation under the `acks` config; do not treat it as end-to-end processing confirmation.
- Handle both synchronous exceptions from calling `send()` and asynchronous exceptions from the future.
- Use `whenComplete()` to observe both success and failure; use other stages when transforming or chaining work.
- Keep default callbacks short. Offload heavy work to a bounded executor.
- Limit `get()` and `join()` on high-load request-serving or consumer threads.
- Configure `acks`, idempotence, and delivery timeout per durability requirements.
- Never retry blindly on timeouts; a send may have been written by the broker even if the application missed the ACK.
- Keep `eventId` stable, combined with consumer idempotency or outbox to control duplicates.
- With Kafka transactions, distinguish send future completion from transaction commit.
- Log and emit metrics sufficient to link producer events to records and consumers later.

`CompletableFuture` lets applications handle Kafka send results without blocking threads waiting on brokers. Reliability still depends on how the producer acknowledges, how the application propagates errors, retry policies, and consumers' ability to handle redelivery safely. When these boundaries are clearly designed, callbacks become a dependable observability and orchestration layer in the event-publishing pipeline.