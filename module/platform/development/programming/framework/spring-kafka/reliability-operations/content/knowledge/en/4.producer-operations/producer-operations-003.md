# ProducerListener

## 1. ProducerListener in Spring Kafka

`ProducerListener<K, V>` is a Spring Kafka-level callback for observing the result of sending records through a `KafkaTemplate<K, V>`. It lets the application know whether a send succeeded or failed after the Kafka producer completes its corresponding callback.

ProducerListener is commonly used for cross-cutting tasks across many sends:

- Centralized logging when a record is sent successfully or encounters an error.
- Recording metrics on successful sends, failed sends, and exception types.
- Collecting metadata such as topic, partition, offset, and timestamp.
- Adding information to support tracing, incident investigation, and producer operations.

ProducerListener does not send records itself, does not choose partitions, does not configure retries, and does not determine broker acknowledgement levels. It observes results from the send path managed by KafkaTemplate and the Kafka client.

A typical send has the following flow:

~~~mermaid
sequenceDiagram
    participant S as Service
    participant T as KafkaTemplate
    participant P as KafkaProducer
    participant B as Broker
    participant PL as ProducerListener
    participant F as Send Future

    S->>T: send(topic, key, value)
    T->>P: send(record, callback)
    P->>P: serialize, partition, batch
    P->>B: Produce request
    B-->>P: Produce response
    P->>PL: onSuccess or onError
    P->>F: complete future
    F-->>S: SendResult or exception
~~~

The diagram illustrates the main components. The exact ordering between invoking ProducerListener and completing the future belongs to the implementation of the running Spring Kafka version; the application should treat them as two ways to receive the result of the same send and not depend on callback order to coordinate business logic.

## 2. Methods of ProducerListener

The interface has two key callbacks:

~~~java
public interface ProducerListener<K, V> {

    default void onSuccess(
        ProducerRecord<K, V> producerRecord,
        RecordMetadata recordMetadata
    ) {
    }

    default void onError(
        ProducerRecord<K, V> producerRecord,
        RecordMetadata recordMetadata,
        Exception exception
    ) {
    }

    default boolean isInterestedInSuccess() {
        return false;
    }
}
~~~

The methods above represent the common API in Spring Kafka 2.x/3.x. Check the Javadoc of your actual dependency if the project uses a different version.

### 2.1. onSuccess

`onSuccess(ProducerRecord, RecordMetadata)` is invoked when the Kafka producer reports a successful send under the configured acknowledgement mechanism. The two parameters provide:

- `ProducerRecord`: the record sent by the application, including topic, partition if specified, timestamp, key, value, and headers.
- `RecordMetadata`: metadata returned by the broker, typically including topic, partition, offset, timestamp, and record size.

By default, `isInterestedInSuccess()` returns `false`. To receive success callbacks, the implementation must override this method and return `true`. This prevents listeners that only care about errors from having to process success callbacks for every record.

### 2.2. onError

`onError(ProducerRecord, RecordMetadata, Exception)` is invoked when a send completes with an error. The exception is the primary source for classifying the cause; metadata may be absent, so never assume partition or offset is always available.

Common causes include:

- The serializer cannot convert the key or value to bytes.
- Unable to fetch topic metadata or producer buffer space within the allowed time.
- Connection loss, unavailable broker, or request timeout.
- Broker rejects the write due to authorization, record size, or ISR conditions.
- Delivery timeout expires after retry attempts without the producer receiving a successful result.

ProducerListener only receives error notifications. It does not retry on its own, does not modify the record, and does not change producer configuration. Internal retry policy is still executed by the Kafka producer; the listener observes the final outcome of the send.

### 2.3. isInterestedInSuccess

`isInterestedInSuccess()` tells KafkaTemplate whether the implementation needs success callbacks. The default value is `false`. When only error tracking is needed, keeping the default reduces callback work on the send path.

If success logging or metrics are needed, override it to return `true`. Avoid enabling success callbacks just to perform unnecessary work for each record, especially on high-throughput topics.

## 3. Implementing a ProducerListener

A single implementation is typically shared across sends through a KafkaTemplate:

~~~java
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.support.ProducerListener;
import org.springframework.stereotype.Component;

@Component
public class OrderProducerListener
        implements ProducerListener<String, OrderCreated> {

    private static final Logger log =
        LoggerFactory.getLogger(OrderProducerListener.class);

    @Override
    public boolean isInterestedInSuccess() {
        return true;
    }

    @Override
    public void onSuccess(
        ProducerRecord<String, OrderCreated> record,
        RecordMetadata metadata
    ) {
        log.info(
            "Kafka publish succeeded: topic={}, partition={}, offset={}, key={}",
            metadata.topic(),
            metadata.partition(),
            metadata.offset(),
            record.key()
        );
    }

    @Override
    public void onError(
        ProducerRecord<String, OrderCreated> record,
        RecordMetadata metadata,
        Exception exception
    ) {
        Integer partition =
            metadata == null ? null : metadata.partition();

        log.error(
            "Kafka publish failed: topic={}, partition={}, key={}",
            record.topic(),
            partition,
            record.key(),
            exception
        );
    }
}
~~~

The example uses generic types matching the template's key and value types. When there are multiple event types, you can use a common listener with broad types or register dedicated listeners per KafkaTemplate to log accurate business metadata. Avoid unsafe value casting inside a listener shared across multiple templates.

In the error callback, metadata is handled in a null-safe manner. If the producer has not received broker metadata yet, the application can still log the topic and key from `ProducerRecord` along with the exception for investigation.

In real environments, carefully consider what data gets logged. Keys may contain customer IDs or sensitive information; do not log entire payloads if payloads contain personal data. Use a controlled event ID or correlation ID for tracing when needed.

## 4. Registering ProducerListener with KafkaTemplate

ProducerListener is attached to a KafkaTemplate. Every send through that template goes through the configured listener.

### 4.1. When creating KafkaTemplate manually

~~~java
@Configuration
public class OrderKafkaConfiguration {

    @Bean
    public ProducerListener<String, OrderCreated> orderProducerListener() {
        return new OrderProducerListener();
    }

    @Bean
    public KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
        ProducerFactory<String, OrderCreated> producerFactory,
        ProducerListener<String, OrderCreated> orderProducerListener
    ) {
        KafkaTemplate<String, OrderCreated> template =
            new KafkaTemplate<>(producerFactory);

        template.setProducerListener(orderProducerListener);
        return template;
    }
}
~~~

`setProducerListener(...)` sets the listener on the template. Exact bean creation may differ if the application uses Spring Boot auto-configuration, multiple producer factories, or transactional templates. When using a Boot auto-configured template, configure the listener on the exact template injected into services; do not create a second KafkaTemplate that services do not use.

If multiple templates send to different Kafka clusters or data types, each template can have its own ProducerListener. This helps separate metrics and logs by stream while keeping generic types accurate.

### 4.2. Default listener

A standard KafkaTemplate has a default listener to log send failures, typically `LoggingProducerListener`. This implementation serves basic error logging. When metrics, correlation, or business-specific logging are needed, the application can replace it with a custom implementation.

Do not assume a custom listener is automatically attached to every KafkaTemplate in the application. Check how template beans are created and make sure the listener is attached to the right instance.

## 5. ProducerListener and CompletableFuture

In Spring Kafka 3.x, `KafkaTemplate.send(...)` returns `CompletableFuture<SendResult<K, V>>`. ProducerListener and the future both observe the send result, but serve two different needs.

| Mechanism | Scope | Purpose |
|---|---|---|
| ProducerListener | Centralized on KafkaTemplate | Logging, metrics, and shared observability across sends |
| CompletableFuture | Per send call | Composing async flows and handling results at the call site |
| Callback passed to KafkaProducer | Low-level Kafka client API | Custom producer-layer handling when truly necessary |

Example of using the future in a service:

~~~java
public CompletableFuture<SendResult<String, OrderCreated>> publish(
    OrderCreated event
) {
    return kafkaTemplate
        .send("orders", event.orderId(), event)
        .whenComplete((result, error) -> {
            if (error != null) {
                log.warn("Publish did not complete for event {}", event.eventId(), error);
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();
            log.debug(
                "Published event {} to {}-{} at offset {}",
                event.eventId(),
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });
}
~~~

ProducerListener is suited for shared behavior at the template level. The future is suited when the service needs to return a result to the caller, combine multiple sends, update a command's status, or execute a next step that depends on the outcome.

There is no need to duplicate the same log or metric in both ProducerListener and the future callback. If both record the same success/error event, counts may be doubled. Clearly decide who owns metrics and who handles business logic.

Prior to Spring Kafka 3.0, send methods commonly used `ListenableFuture`; starting in 3.0 they use `CompletableFuture`. Older examples may need adjustment when upgrading.

## 6. Callback timing and the meaning of success

### 6.1. What does success mean?

`onSuccess` indicates that the Kafka producer completed the send under the active producer configuration. The meaning of the acknowledgement depends on `acks`:

| Configuration | What the success callback indicates |
|---|---|
| `acks=0` | The client completed sending without waiting for broker acknowledgement |
| `acks=1` | The leader acknowledged per protocol after writing |
| `acks=all` | Replicas in the ISR satisfied Kafka's acknowledgement condition |

Therefore, success does not mean the consumer has read the record, the listener has processed it, the database has committed, or a business transaction has completed. ProducerListener is an observation point for the producer-side send outcome.

### 6.2. Transactions may not be committed yet

With Kafka transactions, a record may be acknowledged by the producer as sent successfully while the transaction is still open. The transaction may later commit or abort. Therefore, a record's success callback does not prove the record has become committed data visible to consumers using `read_committed`.

If you need the transaction outcome, observe the result at the transaction boundary—for example, the outcome of `executeInTransaction` or an appropriate transaction synchronization mechanism. Do not rely solely on ProducerListener to conclude that a multi-record transaction has committed.

A Kafka transaction only covers the Kafka operations participating in that transaction. It does not automatically create a distributed transaction across databases or HTTP services.

### 6.3. Callback ordering

An application may send multiple records concurrently to multiple partitions. Callbacks complete according to producer and broker progress; there is no global order across partitions. Do not use ProducerListener invocation order to infer business ordering across an entire topic.

If ordering is required, choose keys and partitions appropriately. Kafka guarantees record order within a single partition; ProducerListener merely observes each send's outcome.

## 7. Does ProducerListener handle retries?

No. The Kafka producer manages internal retries based on client configurations such as `retries`, `retry.backoff.ms`, `request.timeout.ms`, and `delivery.timeout.ms`. ProducerListener receives a callback when the send reaches a final success or error result.

For example, if a request fails transiently, the producer may retry automatically and eventually succeed. In that case, the listener receives `onSuccess`; it does not necessarily receive a separate callback for each internal retry. To observe retry counts, use producer metrics or an appropriate monitoring system.

If all internal retries fail, the listener receives `onError` with the corresponding exception. Do not call `KafkaTemplate.send()` directly inside `onError` as a default retry mechanism:

- It can create an infinite re-send loop.
- The callback may run on the producer thread; re-sending or waiting synchronously can block the send path.
- A timeout does not prove the broker failed to write the record, so re-sending can create duplicates.
- Retrying requires bounded attempts, backoff, error classification, and a stable event ID.

If the business flow needs to retry sending after the application receives an error, coordinate retries at the appropriate layer with attempt limits, backoff, and idempotent mechanisms. For events that must be guaranteed to be published after a database commit, consider a transactional outbox instead of trying to retry inside callbacks.

## 8. Writing production-safe callbacks

ProducerListener is often used as a shared component, and callbacks are invoked on the Kafka producer's completion path. Therefore, callbacks must be brief and safe under concurrency.

### 8.1. Avoid blocking

Do not perform slow operations in `onSuccess`/`onError`:

- Making synchronous HTTP calls to another service.
- Running database queries or waiting on transactions.
- Waiting on another future with `get()` or `join()`.
- Processing large payloads or performing CPU-heavy computations.
- Waiting on locks that may be held by other threads.

A slow callback can slow down the producer's callback processing and hurt throughput. If further processing is needed, offload the work to a separate executor with a bounded queue or another asynchronous mechanism. The executor must have a rejection policy and metrics to prevent unbounded work accumulation.

### 8.2. Thread safety

A ProducerListener may be invoked concurrently for multiple sends. Do not store per-record temporary state in shared mutable fields without proper synchronization.

Avoid writing:

~~~java
public class UnsafeProducerListener
        implements ProducerListener<String, OrderCreated> {

    private String currentOrderId;

    @Override
    public void onSuccess(
        ProducerRecord<String, OrderCreated> record,
        RecordMetadata metadata
    ) {
        currentOrderId = record.key();
        // Other code reads currentOrderId later.
    }
}
~~~

Two callbacks can overwrite each other's values. Use local variables derived directly from callback parameters, or copy the needed data into an immutable object before handing it off to an executor.

### 8.3. Do not let callback errors obscure the send result

Callback logic should have its own exception handling. If code that logs, increments metrics, or publishes internal events can throw an exception, handle that error inside the callback and alert appropriately. Do not let an instrumentation error turn into a new business error or lose information about the original send result.

In particular, avoid invoking ProducerListener directly from recovery code; callbacks should only be called by KafkaTemplate as part of the send lifecycle.

## 9. Using ProducerListener for metrics and tracing

A listener can update metrics for all sends going through a template. Examples of metric groups:

| Metric | Meaning |
|---|---|
| Producer send success count | Number of sends completed successfully |
| Producer send error count | Number of sends completed with failure |
| Send completion latency | Time from send call until callback |
| Error count by exception class | Classification of error groups |
| Success by topic | Tracking publish traffic by topic |
| Missing metadata count | Number of errors lacking broker metadata |

Metric labels should have low cardinality. Topic, outcome, and exception group are usually suitable; event ID, order ID, customer ID, or key should not become metric labels because they can create millions of label series.

For tracing, you can read the correlation ID from record headers and include it in logs or trace context. If trace context needs to be preserved across callback threads, use the context propagation mechanism of your deployed tracing system; do not assume a ThreadLocal from the original request is always present on the callback thread.

Example of updating metrics by topic and outcome:

~~~java
@Override
public boolean isInterestedInSuccess() {
    return true;
}

@Override
public void onSuccess(
    ProducerRecord<String, OrderCreated> record,
    RecordMetadata metadata
) {
    meterRegistry.counter(
        "app.kafka.producer.send",
        "topic", record.topic(),
        "outcome", "success"
    ).increment();
}

@Override
public void onError(
    ProducerRecord<String, OrderCreated> record,
    RecordMetadata metadata,
    Exception exception
) {
    meterRegistry.counter(
        "app.kafka.producer.send",
        "topic", record.topic(),
        "outcome", "error"
    ).increment();
}
~~~

The example needs constructor injection for `MeterRegistry` and exception classification as required. If latency is needed, capture the send start timestamp at the call site or use Spring Kafka and Micrometer's built-in observation/metrics; do not try to infer latency solely from broker metadata.

Do not rely solely on ProducerListener to build the entire producer dashboard. Combine callbacks with Kafka client metrics such as request latency, retry rate, buffer availability, batch size, and record error rate to distinguish application errors from broker or network issues.

## 10. Error handling and application-level recovery

`onError` is the point to record a failure, but the recovery strategy must be designed according to error category and business state.

| Error group | Handling approach |
|---|---|
| Data or serializer error | Fix schema/data; do not infinitely retry the same payload |
| Authorization or configuration | Fix permissions, credentials, or producer configuration |
| Transient broker/network issue | Let the producer retry per config; if final failure occurs, apply bounded business retry |
| Not enough replicas | Check ISR, replication, and `min.insync.replicas` |
| Timeout with unknown outcome | Consider the possibility the record was written; use event ID and consumer idempotency |
| Record size exceeds limit | Reduce payload or adjust limits in a controlled manner |

If the application needs to retain events until sent successfully, the transactional outbox is a common pattern. The service writes business changes and the outbox record in the same database transaction. A separate publisher reads the outbox, sends to Kafka, and updates status upon receiving the result. If the publisher stops after the broker writes the record but before updating the outbox, it may re-send; consumers still need idempotency.

ProducerListener can provide logs/metrics to observe the publisher's results, but does not replace outbox storage, retry scheduling, delivery state, or replay workflows.

## 11. Testing ProducerListener

An implementation can be unit tested independently by invoking callbacks with a `ProducerRecord`, mocked `RecordMetadata`, and sample exceptions. These tests verify that the listener handles metadata, logging/metrics, and null metadata cases properly.

Unit tests can focus on:

- `onSuccess` records success metrics for the right topic.
- `onError` records error metrics and does not assume metadata is always non-null.
- `isInterestedInSuccess` returns `true` when success tracking is needed.
- Callbacks do not call external services or perform blocking operations.
- Shared listeners do not hold prior record state in mutable fields.

At the integration level, use a test broker or Embedded Kafka matching your Spring Kafka version to verify that KafkaTemplate actually invokes the listener on successful sends and when the producer receives errors. For broker errors, design reproducible test scenarios; do not simply throw exceptions manually into the implementation and conclude the Kafka send path has been tested.

Testing the listener in isolation does not prove broker configuration, serializers, `acks`, retries, or transactions work properly. Those parts must be tested at their corresponding integration layers.

## 12. Common pitfalls when using ProducerListener

**Forgetting to override `isInterestedInSuccess()`:** `onSuccess` is not called because the default is usually `false`. If success callbacks are needed, return `true`.

**Assuming metadata always exists:** When a send fails before the broker returns metadata, the `metadata` parameter in `onError` may be null. Always handle it null-safely.

**Using ProducerListener as a retry handler:** The listener has no built-in retry mechanism. Internal retries are managed by the Kafka producer; business retries require limits, backoff, and idempotency.

**Calling databases or HTTP inside callbacks:** Slow callbacks can impact the producer's processing path. Offload necessary work to a bounded executor or a separate worker.

**Logging payloads:** Payloads may contain sensitive data and cause log volume to grow rapidly. Prefer event ID, topic, permitted keys, partition, offset, and exception details.

**Double-counting metrics:** The same send gets recorded by both ProducerListener and the future callback. Designate a single place responsible for shared metrics.

**Treating success as transaction commit:** A successful record callback does not guarantee the transaction committed or consumers processed it. Track transaction outcomes and downstream processing separately.

**Sharing a listener with mutable state:** Concurrent callbacks can overwrite state. Handle data via local variables or immutable objects.

## 13. Investigation workflow when ProducerListener receives onError

When error callbacks appear, trace in order:

1. Record the topic, key or event ID, exception class, and error message.
2. Determine whether the error occurred during serialization, metadata/buffer waiting, broker connection, or broker rejection.
3. Read the exception cause chain; distinguish timeout, authorization, serialization, and ISR errors.
4. Cross-check producer metrics such as retry rate, request latency, buffer availability, and error rate.
5. Check broker/partition health, ISR, and write permissions if the error comes from the broker.
6. Determine whether the outcome is unambiguous. For timeouts, consider the possibility the record was already written before deciding to re-send.
7. If business-layer retries are needed, use a stable event ID, bounded backoff, and consumer-side idempotency.

For success callbacks, store the metadata needed to locate the record by topic, partition, and offset. For error callbacks, do not fabricate partition/offset if metadata is missing; record the exception and the record details the application already knows.

## 14. Operational principles

- Attach ProducerListener to the exact KafkaTemplate used by services.
- Override `isInterestedInSuccess()` only when success callbacks are genuinely needed.
- Handle metadata null-safely in `onError`.
- Keep callbacks short, non-blocking, and safe under concurrent multi-threaded calls.
- Use ProducerListener for centralized logging/metrics; use futures for logic depending on a single send's outcome.
- Do not retry infinitely or blindly re-send after timeouts.
- Distinguish send acknowledgement, transaction commit, and consumer business processing.
- Combine callback metrics with Kafka producer metrics and broker metrics.
- Use stable event IDs together with consumer idempotency or a transactional outbox when event delivery guarantees are required.

ProducerListener provides a consistent observation point for sends via KafkaTemplate. When callbacks are used in their proper role, operations teams can see how sends completed, gather metadata for tracing, and identify producer errors. Stream reliability still depends on Kafka configuration, transactions, retries, and how downstream systems handle duplicates.
