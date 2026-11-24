# Callbacks When Send Completes

When a producer sends a record using **KafkaTemplate**, the send operation usually happens asynchronously. The application does not have to pause the current thread to wait for the broker's response; instead, it receives a future object and registers a callback to handle when the send succeeds or fails.

Callbacks let the producer record the send outcome, read the record's metadata, update metrics, write logs for traceability, and react to failures. This is an important part of building messaging flows with Spring Kafka: emitting an event is not just calling send, but also knowing what the broker acknowledged and what the application must do when the outcome is not as expected.

This lesson belongs to the **Producer** chapter of the **SPRING_KAFKA_MESSAGING** module, focusing on KafkaTemplate callbacks, reading SendResult and RecordMetadata, asynchronous error handling, organizing safe retries, and testing send outcomes.

## Learning objectives

After this lesson, you can:

- Explain why KafkaTemplate sends records asynchronously and when callbacks are invoked.
- Use CompletableFuture and whenComplete in Spring Kafka 3.x.
- Read topic, partition, offset, and timestamp from SendResult.
- Distinguish errors raised immediately during the send call from asynchronous completion errors.
- Log and record metrics in callbacks without slowing down producer I/O.
- Understand the relationship between callbacks, acks, retries, and idempotence.
- Avoid blind retries that generate duplicate events.
- Test both successful and failed send branches.
- Distinguish broker record acknowledgement from consumer business processing.

## 1. Lifecycle of a send operation

KafkaTemplate is Spring Kafka's abstraction for sending records. When send is called, the template hands the record to the Kafka producer. The producer performs serialization, selects a partition, places the record into its buffer, and sends it via the Kafka client's batching/network mechanism.

High-level flow:

~~~mermaid
sequenceDiagram
    participant App as Spring Service
    participant KT as KafkaTemplate
    participant KP as Kafka Producer
    participant Broker as Kafka Broker
    App->>KT: send(topic, key, value)
    KT->>KP: Create and send ProducerRecord
    KT-->>App: CompletableFuture
    KP->>Broker: Produce request
    Broker-->>KP: Produce response
    KP-->>App: Complete future
    App->>App: Success or failure callback
~~~

Key steps:

1. The application calls KafkaTemplate.send with topic, key, and value.
2. KafkaTemplate returns a future for the application to track the result.
3. The Kafka producer serializes key/value and determines the partition.
4. The producer sends the record to the broker managing the partition leader.
5. The broker returns the result according to the producer's acknowledgement configuration.
6. The future completes; the callback receives SendResult or an exception.

Calling send and completing the send are two different points in time. If the application calls get on the future right after send, the current thread blocks until a result or timeout occurs. If it registers a callback, the application can continue other work while the producer handles sending the record.

Callbacks are typically used for lightweight post-processing: recording metadata, incrementing counters, writing logs, or forwarding the result to another coordinating component.

## 2. CompletableFuture in Spring Kafka 3.x

Starting in Spring Kafka 3.0, KafkaTemplate's send methods return CompletableFuture<SendResult<K, V>>. You can use whenComplete to register an action that runs when the future completes, regardless of success or failure.

Simple publisher example:

~~~java
@Service
public class OrderEventPublisher {

    private static final Logger log =
            LoggerFactory.getLogger(OrderEventPublisher.class);

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            OrderCreatedEvent event) {

        CompletableFuture<SendResult<String, OrderCreatedEvent>> future =
                kafkaTemplate.send(
                        "orders.created",
                        event.orderId(),
                        event
                );

        return future.whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                        "Cannot publish order eventId={}, orderId={}",
                        event.eventId(),
                        event.orderId(),
                        exception
                );
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();

            log.info(
                    "Published eventId={}, topic={}, partition={}, offset={}",
                    event.eventId(),
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset()
            );
        });
    }
}
~~~

In the example above:

- KafkaTemplate sends OrderCreatedEvent to topic orders.created.
- orderId is used as the key so records for the same order usually go to the same partition under the default partitioner.
- whenComplete receives two parameters: result and exception.
- On success, SendResult provides metadata from the broker.
- On failure, exception describes why the producer could not complete the send under the current configuration.

To compile the example, import the corresponding types such as CompletableFuture, SendResult, RecordMetadata, and Logger. The example uses the Spring Kafka 3.x API; check your project's dependency version before applying it.

## 3. Reading SendResult and RecordMetadata

SendResult contains the sent ProducerRecord and the RecordMetadata returned by the broker. Metadata helps the application determine where the record was written.

Commonly used fields:

| Field | Meaning |
|---|---|
| topic() | Name of the topic that received the record. |
| partition() | Partition to which the record was written. |
| offset() | Position of the record within that partition. |
| timestamp() | Record timestamp per the returned metadata. |
| serializedKeySize() | Size of the key after serialization. |
| serializedValueSize() | Size of the value after serialization. |

More detailed logging example:

~~~java
future.whenComplete((result, exception) -> {
    if (exception != null) {
        log.error("Kafka send failed for eventId={}", event.eventId(), exception);
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();

    log.info(
            "Kafka send acknowledged: eventId={}, topic={}, partition={}, " +
            "offset={}, timestamp={}, keySize={}, valueSize={}",
            event.eventId(),
            metadata.topic(),
            metadata.partition(),
            metadata.offset(),
            metadata.timestamp(),
            metadata.serializedKeySize(),
            metadata.serializedValueSize()
    );
});
~~~

Offsets only have meaning within a single partition. Do not compare offsets from two partitions as though they belonged to a single global sequence. If you need to trace an event, combine eventId with topic, partition, and offset.

RecordMetadata is useful when investigating failures, measuring traffic, and correlating producer logs with consumer logs. Do not log the entire payload just to track send results; eventId and metadata are usually enough to locate a record in the system.

## 4. Handling both synchronous and asynchronous errors

Not every error surfaces inside the callback. Some errors can arise immediately during the send call, such as invalid producer configuration, serialization errors occurring before the request is sent, or API misuse. Other errors appear when the future completes abnormally, such as timeouts, unavailable brokers, or send failures after internal retries.

Therefore, if the publisher needs to handle both situations, place the send call inside a try/catch while still registering a callback on the future:

~~~java
public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
        OrderCreatedEvent event) {

    try {
        CompletableFuture<SendResult<String, OrderCreatedEvent>> future =
                kafkaTemplate.send(
                        "orders.created",
                        event.orderId(),
                        event
                );

        return future.whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                        "Asynchronous send failed, eventId={}",
                        event.eventId(),
                        exception
                );
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();
            log.info(
                    "Send completed, eventId={}, partition={}, offset={}",
                    event.eventId(),
                    metadata.partition(),
                    metadata.offset()
            );
        });
    } catch (RuntimeException exception) {
        log.error(
                "Send could not be started, eventId={}",
                event.eventId(),
                exception
        );
        throw exception;
    }
}
~~~

Understand the two error paths:

- **Synchronous error:** the send method cannot start or prepare the record; the exception is thrown immediately in the call.
- **Asynchronous error:** the producer accepted the send operation, but the future completes with an exception afterward.

If the publisher catches a synchronous error and returns null, the caller will struggle to distinguish an error from a valid result. Keep the return contract consistent: rethrow synchronous errors for the caller to handle or convert them into a clearly typed error result. Do not silently swallow errors.

In practice, exceptions may be wrapped in CompletionException or ExecutionException depending on how the future is observed. When classifying errors, unwrap the root cause safely and record the event context as well.

## 5. whenComplete, thenAccept, and exceptionally

CompletableFuture offers several ways to chain processing steps. Choose based on the callback's purpose.

| API | When it runs | Purpose |
|---|---|---|
| whenComplete | When the future succeeds or fails | Observe results, log, or record metrics while keeping the original result/exception if the callback does not throw. |
| thenAccept | When the future succeeds | Process SendResult when no new return value is needed. |
| thenApply | When the future succeeds | Transform SendResult into another value. |
| exceptionally | When the future fails | Turn an exception into a fallback value or execute fallback logic. |
| handle | When the future succeeds or fails | Transform both result and exception into a new result. |

Success-only handling example:

~~~java
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

Example of handling errors and returning a fallback result:

~~~java
CompletableFuture<SendResult<String, OrderCreatedEvent>> future =
        kafkaTemplate.send("orders.created", event.orderId(), event);

CompletableFuture<SendResult<String, OrderCreatedEvent>> recovered =
        future.exceptionally(exception -> {
            log.error("Send failed for eventId={}", event.eventId(), exception);
            return null;
        });
~~~

The exceptionally example above only illustrates CompletableFuture's recovery mechanism. Returning null loses type information about the failure and forces callers to check for null. In business applications, use an explicit result type or let the future remain failed so the caller can decide.

When you only need to observe the send outcome without transforming the result, whenComplete is usually appropriate. If you want to turn errors into a business result, design a dedicated result type instead of hiding failures behind null.

## 6. Which thread does the callback run on?

A callback should not be treated as part of the request thread calling the publisher. The future is usually completed by the producer's result-handling thread; a synchronous callback like whenComplete may run on the thread completing the future.

Therefore, callbacks should perform short, non-blocking work:

- Write structured logs.
- Update counter or timer metrics.
- Record topic, partition, and offset.
- Signal a bounded internal queue.
- Complete another future or notify a coordinating component.

Avoid the following inside synchronous callbacks:

- Slow HTTP calls or synchronous database queries.
- Calling Thread.sleep.
- Waiting on another future with get or join.
- Running unbounded retry loops.
- Writing files or performing lengthy large-payload processing.

If post-processing is time-consuming, use whenCompleteAsync with an application-managed Executor:

~~~java
future.whenCompleteAsync((result, exception) -> {
    if (exception != null) {
        failureHandler.record(event.eventId(), exception);
        return;
    }

    successHandler.record(
            event.eventId(),
            result.getRecordMetadata()
    );
}, callbackExecutor);
~~~

The Executor needs appropriate thread and queue bounds, a clear task rejection policy, and lifecycle management by Spring. If the queue fills up, the application needs metrics and a handling strategy; do not spawn unbounded new threads to run callbacks.

Do not use an executor arbitrarily just to switch threads. Moving the callback to an executor does not make Kafka sends faster; it only decouples post-processing work from the send-completion thread.

## 7. What does a successful callback mean?

A successful callback means the producer received a successful outcome according to its acknowledgement configuration. The level of acknowledgement depends on the acks property:

| acks | General meaning |
|---|---|
| 0 | Producer does not wait for broker acknowledgement. Completion does not prove the broker wrote the record. |
| 1 | Leader confirms the record was written to the leader's local log. |
| all | Leader waits for replicas in the ISR to satisfy acknowledgement requirements per cluster configuration, including min.insync.replicas. |

For critical business events, you typically need to evaluate acks=all combined with an appropriate replication factor and min.insync.replicas. This configuration increases data protection, though a send can fail when the ISR does not meet the requirement.

Even when a callback succeeds, it does not mean:

- A consumer has polled the record.
- A listener has processed it successfully.
- The consumer's database has committed.
- A downstream service has completed the business action.
- The entire distributed transaction has completed.

Callbacks reflect the producer's send result at the Kafka boundary. If you need to know the processing outcome on the consumer side, design explicit business feedback, such as a result event, processing status, or a query API.

## 8. Producer retries and application retries

The Kafka producer has an internal retry mechanism. Settings such as retries, delivery.timeout.ms, request.timeout.ms, and reconnect backoff affect how long the producer attempts to resend before the future completes.

When the producer is configured with idempotence appropriately, Kafka can prevent duplicate writes caused by internal retries of the same producer session within the guarantees of the idempotent producer. Modern Spring Kafka and Kafka clients may enable idempotence by default in many compatible configurations; verify your effective configuration and version.

Do not assume that when a callback fails you can immediately call send again. Some failures like timeouts can create an uncertain state: the client did not receive an acknowledgement, yet the broker may have written the record. If the application resends the same event, duplicate records can appear.

A safe strategy should consider:

1. Assigning a stable eventId to every business event.
2. Using producer idempotence to protect internal retries within Kafka's supported scope.
3. If the application must retry after a future fails, keeping the original eventId and payload intact.
4. Allowing consumers to handle duplicates safely via an inbox, unique constraints, or an idempotency key.
5. For data written to a database and then emitted to Kafka, considering the outbox pattern to avoid losing events between the two operations.

Example of a callback that simply records failures and forwards the event to a controlled retry queue:

~~~java
future.whenComplete((result, exception) -> {
    if (exception != null) {
        retryQueue.submit(new FailedPublish(
                event.eventId(),
                event,
                exception
        ));
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();
    metrics.recordPublished(metadata.topic());
});
~~~

retryQueue here is an illustrative component. In real applications, the queue must have bounds, a backoff policy, a maximum attempt limit, durable persistence if needed, and handling for when the queue is full. Otherwise, Kafka outages can cause application memory to grow uncontrollably.

Do not retry infinitely inside a callback. Once the threshold is exceeded, record the failure state for operations or route to a separate handling flow. Producer retries also differ from consumer retries: the producer retries writing the record; the consumer retries processing a record already read.

## 9. Combining callbacks with transactions

In a normal send flow, the future completes when the producer receives the send result per the acks setting. If records are sent inside a Kafka transaction, broker acknowledgement of an individual send does not mean the transaction has committed.

For example, a transaction may send multiple records and then commit or abort all of them together. The application must observe the transaction outcome at the transaction boundary, rather than relying only on individual send callbacks.

A consume-transform-produce flow might:

1. Receive an input record.
2. Start a transaction.
3. Send one or more output records.
4. Commit the input offset within the same transaction per Spring Kafka configuration.
5. Commit the transaction.

If the transaction aborts, output records are not visible to consumers using isolation.level=read_committed. Therefore, do not use a "send callback success" log as proof that the whole transaction committed. Record the transaction's commit/abort status separately.

Kafka transactions also do not automatically cover external databases or APIs. If business logic updates a database, idempotency or outbox/inbox is required to ensure consistency across those boundaries.

## 10. Testing success and failure send callbacks

Testing callbacks should verify both the send result and post-processing actions. Unit tests with a mocked KafkaTemplate are useful for testing how the publisher reacts to a succeeding or failing future; integration tests with a real broker verify serialization, networking, metadata, and acknowledgements.

Example of testing a successful send in an integration test:

~~~java
@Test
void shouldPublishEventAndReceiveMetadata() throws Exception {
    OrderCreatedEvent event = new OrderCreatedEvent(
            "evt-1001",
            "order-1001",
            Instant.now(),
            new BigDecimal("125.50")
    );

    SendResult<String, OrderCreatedEvent> result =
            kafkaTemplate.send(
                    "orders.created",
                    event.orderId(),
                    event
            ).get(10, TimeUnit.SECONDS);

    RecordMetadata metadata = result.getRecordMetadata();

    assertThat(metadata.topic()).isEqualTo("orders.created");
    assertThat(metadata.partition()).isGreaterThanOrEqualTo(0);
    assertThat(metadata.offset()).isGreaterThanOrEqualTo(0);
}
~~~

This test waits for the future to complete because it is test code; in production processing flows, do not block with get without a clear reason. The broker and topic must be initialized in the test context, such as with EmbeddedKafka or Testcontainers.

To test callbacks, register whenComplete and use Awaitility or an auxiliary CompletableFuture to wait for the callback signal. Do not use a fixed Thread.sleep to guess when the callback has run.

Scenarios to include:

- Successful send and callback receives RecordMetadata.
- Unavailable broker or producer timeout and callback receives an exception.
- Serialization failure before sending and publisher handles the synchronous error.
- Callback records metrics or logs the right eventId.
- Callback does not block the producer thread with slow I/O.
- Bounded retries without creating duplicate business effects.
- Aborted transaction is not mistakenly recorded as a committed transaction.

## 11. Monitoring send outcomes in production

Callbacks are a convenient place to update certain producer metrics, but meaningful indicators must be chosen:

- Count of successful and failed sends.
- Duration from calling send to future completion.
- Error count by exception type.
- Timeout or broker error rate.
- Number of callback post-processing tasks rejected by the executor.
- Number of events awaiting retry and events exceeding the retry threshold.

Logs should include eventId, topic, appropriate business key, partition, and offset on success. On failure, log the exception and enough context to diagnose the root cause. Avoid logging sensitive payloads or credentials.

If measuring latency, record the time send starts and the time the callback completes. This is the client-side end-to-end duration of the producer operation, affected by serialization, batching, network, broker, and acknowledgement. It is not consumer processing time.

Metrics need bounded-cardinality tags. Do not use eventId or orderId as metric labels because the number of values can grow very large. Those IDs belong in logs or traces.

## 12. Older Spring Kafka versions

The main examples in this lesson use CompletableFuture, suitable for Spring Kafka 3.0 and later. In older Spring Kafka 2.x versions, KafkaTemplate.send returned ListenableFuture and callbacks were commonly registered via addCallback.

Example using the older API:

~~~java
ListenableFuture<SendResult<String, OrderCreatedEvent>> future =
        kafkaTemplate.send("orders.created", event.orderId(), event);

future.addCallback(
        result -> {
            RecordMetadata metadata = result.getRecordMetadata();
            log.info(
                    "Published to {} partition {} offset {}",
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset()
            );
        },
        exception -> log.error("Kafka send failed", exception)
);
~~~

Do not mix the two API styles in the same example. When upgrading from Spring Kafka 2.x to 3.x, update future handling and audit code using ListenableFuture.

## 13. Capstone exercise: publisher with callbacks and safe retries

Build an OrderEventPublisher that sends OrderCreatedEvent to topic orders.created.

Requirements:

1. Use KafkaTemplate<String, OrderCreatedEvent> to send events with orderId as the key.
2. Return CompletableFuture<SendResult<String, OrderCreatedEvent>> to the caller.
3. Register whenComplete to handle both success and failure.
4. On success, record eventId, topic, partition, offset, and completion duration.
5. On failure, log the exception and forward details to a bounded retry component.
6. Catch synchronous errors that may arise directly inside the send call.
7. Configure producer acknowledgements and idempotence according to durability requirements.
8. Write an integration test verifying metadata after a successful send.
9. Write a failure test verifying the callback receives the exception and retries do not loop infinitely.
10. Add an idempotent consumer to prove resending the same eventId does not repeat business side effects.
11. If Kafka transactions are enabled, test send acknowledgement and transaction commit/abort separately.
12. Track metrics for send success, failure, and completion duration.

The exercise is complete when the publisher can send asynchronously, return clear results, observe metadata, handle both synchronous and asynchronous errors, and enforce a retry policy that causes neither infinite loops nor duplicate effects.

## 14. Learning sequence and completion criteria

| Stage | Core focus | Self-check criteria |
|---|---|---|
| 1. Send lifecycle | KafkaTemplate and producer | Can describe from the send call to the broker result. |
| 2. Future | CompletableFuture and whenComplete | Registers success/failure callbacks properly. |
| 3. Metadata | SendResult and RecordMetadata | Can read topic, partition, offset, and timestamp. |
| 4. Error handling | Synchronous and asynchronous errors | Distinguishes and handles both error paths. |
| 5. Threading | whenCompleteAsync and Executor | Does not block producer completion threads with slow tasks. |
| 6. Acknowledgement | acks, retries, idempotence | Can explain the acknowledgement guarantee represented by callback success. |
| 7. Reliability | Retry, eventId, idempotency, outbox | Bounded retries and consumers tolerate duplicate records. |
| 8. Transaction | Send result and commit/abort | Does not confuse send acknowledgement with transaction commit. |
| 9. Testing/Monitoring | Integration tests, metrics, logs | Has success/failure tests and observable send outcomes. |

The lesson is complete when you can use KafkaTemplate callbacks to observe send results, read metadata, handle errors without blocking the producer, and clearly explain the limits of acknowledgements. Callbacks tell the application the producer-side outcome; end-to-end reliability of the flow also depends on acks, retries, idempotence, transactions, and the consumer's ability to handle duplicates safely.

