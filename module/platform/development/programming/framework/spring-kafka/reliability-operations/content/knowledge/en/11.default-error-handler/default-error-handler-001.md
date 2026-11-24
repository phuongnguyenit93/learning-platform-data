# Role of DefaultErrorHandler

In Spring Kafka, `DefaultErrorHandler` is a listener-container-level error handler used to handle exceptions thrown when a listener processes a record or batch. It decides whether a failed record is retried, the interval between attempts, when to move to recovery, and whether the offset is acknowledged after recovery succeeds.

`DefaultErrorHandler` implements `CommonErrorHandler` and is the replacement for older error handlers such as `SeekToCurrentErrorHandler` in modern Spring Kafka versions. It helps applications centralize retry and recovery policies in container configuration instead of writing manual retry loops inside each listener.

An error handler does not make business logic succeed automatically. It orchestrates error handling at the Kafka listener layer. The application must still classify errors, choose an appropriate backoff, decide where to store unprocessable records, and design idempotency for redeliveries.

## 1. Where Does DefaultErrorHandler Sit in the Processing Flow?

The listener container manages the consumer, polls records, invokes the listener, and acknowledges offsets. When a listener throws an exception, the container delegates error handling to the configured error handler. With `DefaultErrorHandler`, the high-level sequence is as follows:

```text
Kafka consumer poll()
        |
        v
Listener receives record
        |
        v
Execute business logic
        |
        +---- success --------> container continues per AckMode
        |
        +---- exception ------> DefaultErrorHandler
                                  |
                                  v
                           Classify exception
                                  |
                       +----------+----------+
                       |                     |
                 Retry allowed       No retry / retries exhausted
                       |                     |
                       v                     v
                 BackOff then retry      Recoverer
                                             |
                                  +----------+----------+
                                  |                     |
                              Recovery OK         Recovery failed
                                  |                     |
                                  v                     v
                           Handle offset per      Record may be
                           container config       redelivered / retried
```

The error handler operates within the lifecycle of the listener container. It is neither a business service nor a separate listener. Configure the handler on the container factory so that listeners using that factory share the same error-handling policy.

## 2. Main Responsibilities of DefaultErrorHandler

`DefaultErrorHandler` handles several related responsibilities:

- **Exception classification:** determines which exceptions can be retried and which are considered unrecoverable via retry.
- **Retry:** re-invokes record processing according to the container's retry policy.
- **Backoff:** waits between attempts to avoid sending bursts of requests to a failing dependency.
- **Recovery:** after attempts are exhausted, invokes a `ConsumerRecordRecoverer` to log, send the record to a DLT, or perform another recovery action.
- **Managing resumption of consumption:** coordinates seeking or record redelivery mechanisms depending on configuration and Spring Kafka version.
- **Offset coordination:** after the error handler finishes without throwing an exception, the container decides whether to acknowledge the offset according to the acknowledgment configuration.

Separating error policy from the listener lets the listener focus on business logic. The listener only needs to throw an exception when it cannot complete processing; the container and handler take care of retry/recovery according to the shared configuration.

## 3. Basic Configuration

A common configuration creates a `DefaultErrorHandler` with `DeadLetterPublishingRecoverer` and `FixedBackOff`:

```java
@Configuration
public class KafkaErrorConfiguration {

    @Bean
    DefaultErrorHandler defaultErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
        var backOff = new FixedBackOff(1_000L, 2L);

        return new DefaultErrorHandler(recoverer, backOff);
    }
}
```

In this example, `FixedBackOff(1_000L, 2L)` waits one second between retry attempts and allows two retries after the initial delivery. If the initial attempt and both retries fail, the handler invokes the recoverer. In total, the listener may be called three times for that record before recovery.

Attach the handler to `ConcurrentKafkaListenerContainerFactory`:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, Order> orderListenerFactory(
        ConsumerFactory<String, Order> consumerFactory,
        DefaultErrorHandler defaultErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, Order>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(defaultErrorHandler);
    return factory;
}
```

A listener uses this factory via `containerFactory`:

```java
@KafkaListener(
        topics = "${app.topics.orders-in}",
        containerFactory = "orderListenerFactory")
public void onOrder(Order order) {
    orderService.process(order);
}
```

If an application has multiple listener groups with different requirements, you can create multiple factories and attach a dedicated error handler to each group. Avoid changing the application-wide retry policy just to accommodate one special listener.

## 4. Retry and BackOff

Retry is when the container attempts to process a record again after the listener fails. Backoff is the wait period between attempts. If you retry immediately while a dependency is experiencing an outage, the application may generate additional load and prolong the failure.

Spring Kafka supports backoff strategies from Spring Framework, such as:

| Strategy | How It Works | When Appropriate |
|---|---|---|
| `FixedBackOff` | Waits a fixed interval between attempts | Transient errors with a relatively stable recovery time. |
| `ExponentialBackOff` | Increases the wait time after each failure | Dependencies that need longer recovery time when failures persist. |
| `ExponentialBackOffWithMaxRetries` | Exponentially increasing backoff with a cap on retry attempts | Need to control both wait duration and total number of attempts. |

Example using fixed backoff:

```java
var backOff = new FixedBackOff(2_000L, 3L);
var handler = new DefaultErrorHandler(recoverer, backOff);
```

This example allows three retries after the initial attempt, with a two-second wait between attempts. Distinguish the number of retries from the total number of times the listener is invoked: the initial delivery is not counted as a retry.

With exponential backoff, you can configure the initial interval, multiplier, and wait limits:

```java
var backOff = new ExponentialBackOff(1_000L, 2.0);
backOff.setMaxInterval(10_000L);
backOff.setMaxElapsedTime(60_000L);

var handler = new DefaultErrorHandler(recoverer, backOff);
```

Specific values must be chosen based on the dependency's recovery time and the flow's SLA. Retrying for too long can hold back a partition, increase consumer lag, and delay subsequent records. Retrying too briefly can create repeated load against an unhealthy system.

### 4.1 Retry Is Not a Loop Inside the Listener

Do not write a `while` or `for` loop to retry business logic inside the listener if the container already manages retries. An internal loop can hold the consumer thread for too long, causing `max.poll.interval.ms` to be exceeded and making attempt tracking difficult.

Instead, let the exception propagate out of the listener:

```java
@KafkaListener(topics = "${app.topics.orders-in}")
public void onOrder(Order order) {
    orderService.process(order); // Throw exception if retry is needed
}
```

If you catch an exception to log it, rethrow it when you want the container to retry. If you catch and swallow it, the container may treat the listener as having completed normally and the offset may be acknowledged.

## 5. Exception Classification: Which Errors Should Be Retried?

Not every exception can be resolved by retrying. For example, a connection timeout to a customer service may be transient; a payload missing a required field will usually fail the same way on every retry.

`DefaultErrorHandler` has a default exception classification. Certain conversion and message-mapping errors, such as deserialization or message conversion failures, are treated as non-retryable by default because retrying the same data usually does not make the record valid. Other exceptions are generally retryable unless the application changes the classification.

You can mark business exceptions as non-retryable:

```java
var handler = new DefaultErrorHandler(recoverer, backOff);
handler.addNotRetryableExceptions(
        InvalidOrderException.class,
        UnsupportedCurrencyException.class);
```

Or explicitly mark error types that should be retried:

```java
var handler = new DefaultErrorHandler(recoverer, backOff);
handler.addRetryableExceptions(
        PartnerUnavailableException.class,
        TemporaryDatabaseException.class);
```

Build classification around business causes rather than solely technical exception names. A `RuntimeException` can wrap either a permanent or a transient error; if needed, inspect the cause chain and define specific exceptions at the service layer.

| Error Type | Example | Typically Appropriate Policy |
|---|---|---|
| Transient error | Timeout, connection reset, HTTP 503 | Bounded retry with backoff. |
| Invalid data error | Missing ID, incompatible schema | Do not retry; route to recovery/DLT. |
| Permanent business error | Order state does not allow the operation | Do not retry or route to a separate business handling flow. |
| Configuration error | Wrong credentials, endpoint, or serializer | Alert and fix configuration; continuous retries rarely help. |

## 6. Recovery After Retries Are Exhausted

When attempts are exhausted, `DefaultErrorHandler` invokes the recoverer. The recoverer is the component that decides what to do with an unprocessable record. It may log, store in a quarantine store, publish to a Dead Letter Topic, or trigger another business workflow.

If no custom recoverer is provided, the handler defaults to a logging recoverer to record the failed record. This can be useful during development or when operational policy requires logging only, but logs are not durable storage for replaying records.

### 6.1 Dead Letter Topic

`DeadLetterPublishingRecoverer` sends failed records to another topic for investigation or reprocessing. Basic usage:

```java
var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
var handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L));
```

Under the common default convention, a record from topic `orders` is sent to `orders.DLT` and preserves the corresponding partition. The DLT topic therefore needs enough partitions to accommodate the partition mapped from the source topic. You can configure a custom destination resolver if you want a different DLT naming scheme or routing by exception/topic.

The DLT should retain information that aids investigation and replay:

- Source topic, partition, and offset.
- Key, timestamp, and original payload.
- Exception type, message, and stack trace in headers added by the recoverer.
- Event ID, correlation ID, or trace context if provided by the source.

Do not include sensitive payloads in logs or the DLT if data policies prohibit it. A DLT is part of the data lifecycle and requires clear retention, access control, and handling procedures.

### 6.2 Recovery Failure

If the recoverer cannot send the record to the DLT or the recovery operation throws an exception, the record has not been successfully recovered. Depending on configuration and container state, the record may be retried or re-enter error handling. Do not acknowledge the offset as if recovery completed if the record has not been safely persisted.

Monitor DLT publishing failures separately from listener failures. A system might handle normal listener traffic fine while the DLT broker/topic/serializer is broken, preventing recovery from completing.

## 7. Offsets After Recovery and Acknowledgment

After the error handler finishes without throwing an exception, the container must decide whether to acknowledge the offset of the recovered record. By default, `DefaultErrorHandler` allows the container to acknowledge after the handler completes normally (`ackAfterHandle` defaults to `true`). This behavior can be changed if the application has special requirements.

Example:

```java
handler.setAckAfterHandle(false);
```

When `ackAfterHandle` is disabled, the container does not automatically acknowledge the record simply because the error handler returned normally. You need to understand the impact of AckMode and how the listener container continues processing to avoid unintended record redelivery.

`DefaultErrorHandler` also provides the `commitRecovered` option. When enabled, the handler can commit the offset of a recovered record via the supported mechanism; with this configuration, the container must use `AckMode.MANUAL_IMMEDIATE` to commit the recovered record immediately on the consumer thread:

```java
var handler = new DefaultErrorHandler(recoverer, backOff);
handler.setCommitRecovered(true);
```

Only enable `commitRecovered` when the acknowledgment mode is configured properly and intentionally. Do not enable multiple commit mechanisms simultaneously without clearly understanding which component owns offset acknowledgment.

With `AckMode.MANUAL` or `MANUAL_IMMEDIATE`, the listener explicitly acknowledges when processing succeeds. If the listener throws an exception before acknowledging, the error handler and container coordinate according to manual acknowledgment semantics. Test listener failure, recovery success, and recovery failure with the exact AckMode in use.

## 8. Record Listener and Batch Listener

For a record listener, `DefaultErrorHandler` can identify the failing record and apply retry/recovery to that record. Unprocessed records following it are reprocessed according to the container's seek or resubmission mechanism.

With a batch listener, a single listener invocation receives multiple records. If a batch listener throws a regular exception, the handler does not necessarily know which record in the batch caused the failure. In that case, the entire batch may be retried.

If the listener can identify the failing record, it can throw `BatchListenerFailedException` with the record's index or the record itself:

```java
@KafkaListener(
        topics = "${app.topics.orders-in}",
        containerFactory = "batchListenerFactory")
public void onOrders(List<ConsumerRecord<String, Order>> records) {
    for (int index = 0; index < records.size(); index++) {
        try {
            orderService.process(records.get(index).value());
        }
        catch (RuntimeException ex) {
            throw new BatchListenerFailedException(
                    "Cannot process order in batch", ex, index);
        }
    }
}
```

`BatchListenerFailedException` informs the handler of the failing record's position. The container can commit records prior to that index per the appropriate semantics, then retry or recover the failed record along with the remaining records. Exact handling also depends on AckMode, listener type, and Spring Kafka version.

With batch listeners, clearly define processing order, the possibility that part of the batch already caused side effects, and idempotency for retried records. If the first record succeeds and the third fails, the next batch invocation may re-run the previously processed record.

## 9. Deserialization and Errors Occurring Before the Listener

A record can fail before the `@KafkaListener` method is invoked—for example, when the deserializer cannot convert bytes into an object. In that case, the listener never receives a decoded payload from which to throw an exception itself.

To bring deserialization errors into Spring Kafka's error-handling flow, `ErrorHandlingDeserializer` is typically configured as a wrapper around the actual deserializer. It stores the error information in headers so the container/error handler can handle the failed record and route it to the DLT according to policy.

Example YAML configuration:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
```

This is a skeleton example; the application must configure trusted packages, type mapping, or default target type for the JSON deserializer according to its actual schema. You cannot fix an invalid payload by continuously retrying the same byte sequence; choose an appropriate recovery strategy.

## 10. Seek and Resubmission After Errors

By default, `DefaultErrorHandler` uses a seek mechanism to move the consumer back to the position that needs reprocessing after an exception. Unprocessed records can be redelivered from the appropriate offset in the partition.

In supported Spring Kafka versions, you can configure `seekAfterError(false)` so the container retains unprocessed records and resubmits them to the listener after a short poll to keep the consumer alive. This changes how the container orchestrates redelivery, but does not change the principle: an incomplete record must be reprocessed or explicitly recovered before the offset advances past it.

Do not confuse seek with a retry topic. Seek-based retry keeps the record within the current partition stream and can block subsequent records in the same partition during retry. A retry topic is a different architecture that publishes the record to a retry topic so the consumer can continue processing subsequent records; in exchange, per-partition ordering may change.

## 11. DefaultErrorHandler and Kafka Transactions

`DefaultErrorHandler` is typically used with non-transactional listener containers to manage retry/recovery within the consumer lifecycle. For containers using Kafka transactions, a listener exception triggers a transaction rollback; Spring Kafka uses an `AfterRollbackProcessor`, typically `DefaultAfterRollbackProcessor` by default, to coordinate seeking, retry, and recovery after rollback.

Do not treat `DefaultErrorHandler` as a replacement for a rollback processor in a transactional model. Choose the mechanism based on how the container is configured:

| Listener Model | Error-Handling Mechanism to Consider |
|---|---|
| Container without Kafka transactions | `DefaultErrorHandler` with BackOff and recoverer. |
| Container with Kafka transactions | Rollback and `DefaultAfterRollbackProcessor`/`AfterRollbackProcessor`. |
| Writing Kafka output and committing input offset together | Transaction manager coordinates commits; exceptions lead to rollback and after-rollback flow. |

With transactional listeners, recovery such as sending to a DLT must also be designed around transaction semantics. Configure an appropriate `AfterRollbackProcessor` so that DLT publishing and original offset acknowledgment do not create a data-loss gap. Do not mix non-transactional error handler settings into a transactional container without checking the documentation for your Spring Kafka version.

## 12. Blocking Retry and Retry Topics

`DefaultErrorHandler` typically performs blocking retry: the consumer keeps re-attempting the failed record on that partition according to the backoff. During this time, subsequent records on the same partition may have to wait. This approach fits cases where ordering must be preserved and errors are likely to recover quickly.

Spring Kafka also offers a non-blocking retry-topic model, typically configured via `@RetryableTopic` or the corresponding retry-topic mechanism. Records are forwarded to a retry topic with a delay; the original topic's consumer can continue processing the next records. This can increase throughput during prolonged outages, though it can alter processing order and requires managing more topics.

Do not use retry topics and `DefaultErrorHandler` as two names for the same mechanism. Decide based on ordering requirements, retry duration, partition-blocking tolerance, and operational complexity.

## 13. Observability and Operations

A retry policy is only useful when operations can observe how it behaves. Monitor:

- Listener failure counts by topic, exception type, and consumer group.
- Retry counts, total backoff duration, and recovered record counts.
- Records sent to the DLT and DLT publishing errors.
- Consumer lag per partition during retries.
- Processing latency on first-try success versus success after retry.
- Exception classification, to detect permanent errors being retried or transient errors being sent to the DLT too early.

Logs should include topic, partition, offset, key or event ID, exception class, and delivery attempt if the application enables the delivery-attempt header. Avoid logging full sensitive payloads.

The DLT needs its own dashboard or operational runbook. You need to know who handles records, when to replay, which topic to replay to, and how to prevent side effects from executing twice. Do not replay an entire DLT automatically without checking the schema, root cause, and idempotency.

## 14. Testing DefaultErrorHandler

Integration tests should use a real broker in the test environment, such as Embedded Kafka or Kafka Testcontainers. Verify observable behavior on output topics, the DLT, and consumer offsets.

Recommended scenarios:

1. Listener succeeds on the first attempt; verify no retries occur and output/side effects are correct.
2. Listener fails transiently a few times then succeeds; verify attempt counts and backoff intervals.
3. Listener always throws an exception; verify the recoverer is called after retries are exhausted.
4. Exception is classified as non-retryable; verify recovery occurs without unnecessary retries.
5. Recoverer sends the record to the DLT; verify payload, key, and source metadata.
6. DLT publishing fails; verify the record is not acknowledged as if recovery succeeded.
7. For a batch listener, throw `BatchListenerFailedException` at an index; verify preceding records and the failed record are handled as configured.
8. Send an undeserializable payload; verify `ErrorHandlingDeserializer` and the error handler route the failed record to recovery.
9. Stop the consumer during backoff or retry; verify the record can be redelivered and business logic is idempotent.
10. For a transactional listener, test rollback and `DefaultAfterRollbackProcessor` rather than assuming `DefaultErrorHandler` controls the transaction.

Do not use fixed `Thread.sleep()` calls to conclude that retry or DLT publishing has occurred. Wait on specific conditions such as listener invocation counts, the record appearing in the DLT, or the offset advancing to the expected position, with a finite timeout.

## 15. Common Pitfalls

- **Swallowing exceptions in the listener:** the container may treat processing as successful and not invoke the error handler.
- **Infinite retries without backoff:** overwhelms dependencies and keeps the partition stuck in a prolonged error state.
- **Retrying permanent data errors:** repeats the same invalid payload without being able to fix the root cause.
- **Not configuring a recoverer:** records that exhaust retries are only logged by default, with no durable DLT flow for replay.
- **Not monitoring DLT errors:** recovery may fail silently without the system noticing.
- **Assuming every exception is retried:** some exceptions are classified as fatal/non-retryable by default or by application configuration.
- **Confusing retry count with total invocations:** retry count does not include the initial delivery.
- **Not distinguishing record and batch listeners:** an entire batch may be retried if the handler cannot identify the failing record.
- **Using the wrong mechanism for transactional containers:** transactional listeners require a rollback processor and proper transaction semantics.
- **Assuming DLT replay is always safe:** replay can duplicate side effects if business logic is not idempotent.

## 16. When Should You Use DefaultErrorHandler?

Use `DefaultErrorHandler` when a non-transactional listener container needs a clearly configured retry and recovery policy. It is well-suited for transient errors requiring backoff, invalid records needing a DLT, and applications that want to separate error handling from business logic.

Start by identifying which exceptions are retryable, the number of attempts, and the maximum wait time. Then choose a recoverer, decide how offsets are committed after recovery, and add metrics for retry/DLT. For batch listeners, define how to accurately report the failing record. For transactional listeners, use an appropriate rollback processor to preserve atomicity between output and input offsets.

`DefaultErrorHandler` is the error-orchestration mechanism at the listener container layer. Its effectiveness depends on the application throwing exceptions at the right time, classifying errors according to their true nature, storing failed records safely, and ensuring retries or replays do not cause duplicate side effects.
