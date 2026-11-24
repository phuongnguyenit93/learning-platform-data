# Consumer Retries with Error Handlers

Kafka consumers can encounter transient errors when processing events: a database disconnects for a few seconds, an HTTP service times out, or a dependent system is overloaded. If the listener throws an exception outward, Spring Kafka can hand error handling to an error handler to retry the record under a configured policy. When all attempts are exhausted and failures persist, the application needs a recovery decision, such as sending the record to a dead-letter topic (DLT), logging the failure for manual intervention, or stopping the stream as required by the business.

Consumer retries help resolve self-healing errors, yet they must have clear bounds and offset acknowledgment rules. Infinite retries can stall a partition on one failing record, increase consumer lag, and delay subsequent records. This lesson covers configuring `DefaultErrorHandler`, choosing backoff strategies, classifying exceptions, integrating a DLT, and monitoring retry behavior in Spring Kafka.

## 1. Processing Flow When a Listener Throws an Error

When `@KafkaListener` processes a record, Spring Kafka invokes the listener method inside the listener container. If the method completes normally, the container continues per its `AckMode` and offset commit policy. If the listener throws an exception, the container forwards the error to the configured error handler.

For a record listener, `DefaultErrorHandler` can retry on the current consumer. Once processing succeeds, the container proceeds and acknowledges the offset per configuration. When retries are exhausted, the error handler invokes a recoverer; the recoverer can publish the record to a DLT. If recovery succeeds, the source offset is handled per the handler and container policy. If recovery fails, the record is not treated as successfully recovered and error handling continues.

```mermaid
flowchart TD
    A[Kafka delivers record] --> B[@KafkaListener processes]
    B --> C{Exception?}
    C -->|No| D[Container handles commit per AckMode]
    C -->|Yes| E[DefaultErrorHandler]
    E --> F[Wait per BackOff]
    F --> G[Reprocess record]
    G --> H{Success?}
    H -->|Yes| D
    H -->|No, attempts left| E
    H -->|Exhausted| I[Recoverer]
    I --> J{Recovery succeeded?}
    J -->|Yes| K[Continue per offset policy]
    J -->|No| L[Retain error state and emit operational signal]
```

The primary requirement for retries to work is that the listener must let exceptions propagate out. If a listener catches an exception, only logs it, and returns normally, the container usually treats that invocation as successful and the error handler never receives the error to retry.

```java
@KafkaListener(topics = "orders", groupId = "order-service")
public void consume(OrderEvent event) {
    orderService.process(event); // Exception propagates to the container
}
```

If extra context is needed, log it and rethrow the exception or wrap it in a business exception preserving the cause. Never catch a broad `Exception` and continue as if the record succeeded.

## 2. Configuring `DefaultErrorHandler` and Backoff

`DefaultErrorHandler` is the common error handler provided by Spring Kafka for listener containers. It accepts a `BackOff` to govern wait intervals and retry counts. The following example allows three retries spaced one second apart:

```java
@Configuration
public class KafkaConsumerConfiguration {

    @Bean
    public DefaultErrorHandler kafkaErrorHandler() {
        DefaultErrorHandler handler = new DefaultErrorHandler(
                new FixedBackOff(1_000L, 3L));
        return handler;
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            orderListenerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory,
                    DefaultErrorHandler kafkaErrorHandler) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();
        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(kafkaErrorHandler);
        return factory;
    }
}
```

Listener using the configured factory:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "orderListenerFactory")
public void consume(OrderEvent event) {
    orderService.process(event);
}
```

With `FixedBackOff(1_000L, 3L)`, the first argument is the one-second wait interval and the second is the number of retries after the initial processing attempt. Consequently, a record can be delivered up to four times: one initial attempt plus three retries. If you want only a single processing attempt, configure a no-retry policy instead of confusing retry count with total invocations.

`BackOff` controls retry pacing; it does not turn a permanent error into a transient one. Short pauses fit brief blips; longer pauses reduce pressure on overloaded services while keeping records waiting longer. Choose both the retry count and total wait duration based on expected recovery times and business latency requirements.

## 3. Choosing a Backoff Strategy

Common policies have distinct traits:

| Policy | How it works | When appropriate |
|---|---|---|
| `FixedBackOff` | Waits a constant interval between retries | Transient errors with fairly predictable recovery times; simple configuration. |
| `ExponentialBackOff` | Progressively increases wait interval after each failure, bounded by config | Overloaded dependencies or unpredictable recovery times. |
| Custom backoff | Application decides wait duration based on error type or context | Error categories needing distinct retry policies. |

Example using `ExponentialBackOff`:

```java
ExponentialBackOff backOff = new ExponentialBackOff(500L, 2.0);
backOff.setMaxInterval(10_000L);
backOff.setMaxElapsedTime(60_000L);

DefaultErrorHandler handler = new DefaultErrorHandler(recoverer, backOff);
```

This example starts at 500 ms, multiplies the wait by 2, and caps each interval at 10 seconds. Total backoff time is bounded at roughly 60 seconds per configuration. Check your Spring Kafka version because APIs and total duration calculations for backoff classes can vary between versions.

When choosing a backoff, consider:

- Whether total retry time fits within the maximum wait accepted by the business.
- Whether the listener holds the consumer thread long enough to delay subsequent `poll()` calls.
- Whether the downstream service needs breathing room before receiving the next request.
- Whether multiple consumers are retrying the same failing service simultaneously, creating request spikes.
- How long trailing records in the same partition can wait before processing.

Consumer-side retry typically waits within the consumption thread. If wait durations are long, a failing record can slow progress on that partition. For long delays or when newer records must keep flowing, consider retry topics with `@RetryableTopic`; that is a different model from `DefaultErrorHandler` in-place retry and carries its own trade-offs around ordering, topics, and operations.

## 4. Classifying Exceptions to Avoid Misguided Retries

Not all errors should be retried. Timeouts, temporary connection errors, or 503 responses can clear after a short pause. Invalid data or business rule violations usually do not change just because the application tries again.

Spring Kafka's `DefaultErrorHandler` includes an exception classification mechanism. You can declare non-retryable errors via `addNotRetryableExceptions(...)`, or add retryable errors via `addRetryableExceptions(...)`:

```java
DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 3L));

handler.addNotRetryableExceptions(
        InvalidOrderException.class,
        UnsupportedEventVersionException.class);

handler.addRetryableExceptions(
        TransientDataAccessException.class,
        ResourceAccessException.class);
```

In this example, invalid order data or unsupported event versions go to recovery without going through normal retries. Temporary database or HTTP access errors are retried with backoff. When wrapping exceptions, preserve the cause and verify how the handler classifies the actual exceptions thrown by your listener.

| Error group | Examples | Recommended policy |
|---|---|---|
| Transient | Timeout, brief disconnect, HTTP 503 | Bounded retry with backoff. |
| Invalid data | Missing required field, bad format, disallowed value | No retry; send to DLT or dedicated business workflow. |
| Programming bug | Unexpected null, mapping mismatch, bug | Avoid prolonged repeated retries; alert, investigate, and decide recovery. |
| Deserialization error | Payload cannot convert to object | Handle at deserializer/container layer; listener may never be invoked. |

Spring Kafka treats certain exception types as non-retryable by default because they are usually fatal or unfixable via retries. When altering classifications, inspect your version's default list and override only once you understand the impact. Avoid making every exception retryable, as permanent data errors will waste time and grow lag.

## 5. Routing Failed Records to a DLT

Once retries are exhausted, the error handler needs a recovery action. `DeadLetterPublishingRecoverer` can send the record along with error metadata to a DLT. The example below routes records from `orders` to `orders.DLT` while keeping the source partition:

```java
@Bean
public DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    kafkaTemplate,
                    (record, exception) -> new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 3L));

    handler.addNotRetryableExceptions(InvalidOrderException.class);
    return handler;
}
```

If the resolver preserves partition numbers, the DLT topic needs enough partitions matching the source topic. If the DLT uses a different partition layout, map it explicitly using an appropriate policy. Also ensure the producer has write ACLs to the DLT and serializers can handle the key/value types sent by the recoverer.

When DLT publishing succeeds, the handler can consider the record recovered and continue per offset policy. If publishing fails, keep the recovery failure observable and handled. Never treat calling the recoverer as proof that the record reached the DLT; monitor send outcomes and alert when the DLT fails to receive records.

A DLT needs an owner and a workflow. Track counts entering the DLT, retain source topic/partition/offset, exception, timestamp, and event ID. After fixing data or code, replay under control and ensure consumers are idempotent to prevent duplicate business effects.

## 6. How Retries Affect Offsets and Ordering

Kafka tracks offsets per partition. When a record fails, the error handler decides how to handle that record and any remaining records fetched by the consumer. With a record listener, `DefaultErrorHandler` typically seeks so the consumer re-reads the unsuccessful record on the next poll. Exact commit behavior also depends on `AckMode`, transactions, and container configuration.

Key points to understand:

- Never acknowledge or commit offsets before business work is complete.
- If a record is retried in place, subsequent records in the same partition can be delayed to preserve processing progression.
- Other partitions may continue making progress depending on consumer assignments and activity; do not assume the entire topic halts merely because one partition has a failing record.
- Once a record is successfully sent to a DLT, the source offset can be acknowledged per the recoverer/error handler policy, allowing the partition to advance.
- If the application already wrote to the database before failing prior to offset commit, the record may be redelivered. Business logic must be idempotent or guard against duplicate processing.

With batch listeners, if you need to pinpoint the failing record, Spring Kafka supports `BatchListenerFailedException` carrying the failing record's position. This lets the handler distinguish the processed prefix from the portion needing retry. Report the exact index only when the application is certain of each record's processing status; otherwise, use a suitable full-batch retry policy.

## 7. When Should You Use Retry Topics?

In-place retries with `DefaultErrorHandler` work well for small retry counts and short waits. Because the listener container waits during backoff, a failing record can slow down subsequent processing on that partition. When long delays are needed, new records must keep flowing, or multiple retry tiers with varying wait durations are required, retry topics may be a better fit.

Spring Kafka provides `@RetryableTopic` to route failed records through retry topics and eventually to a DLT. This pattern is commonly used when non-blocking retries are needed so the main consumer thread is not held throughout long waits. However, because retried records are processed on separate topics, ordering among events with the same key can diverge from the original stream. Evaluate ordering requirements, topic count, retention, partitions, replication, and replay processes before choosing it.

| Criterion | In-place `DefaultErrorHandler` retry | Retry topics (`@RetryableTopic`) |
|---|---|---|
| Waiting method | Consumer container waits per backoff | Record is routed to a retry topic with a matching delay |
| Best suited for | Short retries, few attempts, preserving partition progression | Long delayed retries or multi-tier delays |
| Main stream impact | Failing record can block partition progress | Main stream consumer can proceed with other records |
| Ordering | Easier to maintain in-partition progress with in-place retry | Order can shift as records travel through separate topics |
| Operations | Monitor error handler and DLT | Manage additional retry topics, retention, routing, and DLT |

Do not stack multiple retry layers without accounting for total attempts. For instance, three in-place retries combined with three retry-topic attempts can produce more downstream calls than intended. Document one unified retry policy so operations understands the final upper bound.

## 8. Monitoring and Testing Retry Policies

A retry policy is only trustworthy when observable and verified. Monitor at least:

- Listener failure counts and retry counts by exception type.
- Backoff wait durations and total per-record processing time.
- Consumer lag per partition, especially on partitions actively retrying records.
- Successfully recovered records and DLT publish failure counts.
- Records entering the DLT, age of the oldest record, and replayed record counts.
- Error rates and response latencies of databases or downstream services.

Test scenarios should include:

1. Listener fails once then succeeds: verify redelivery and that offsets advance only after completion.
2. Listener always fails: verify retry count matches configured backoff, then recovers per policy.
3. Non-retryable exception: verify unnecessary retries are skipped and the record goes to recovery.
4. DLT unavailable or producer fails: verify the publish failure is surfaced rather than silently marking the record saved.
5. Multiple records in a partition: verify retries do not drop trailing records and ordering matches policy.
6. Consumer restart mid-retry: verify redelivery behavior and idempotency of business logic.
7. Batch listener failing mid-batch: verify offsets and records retry or recover from the right position.

Logs should include topic, partition, offset, key or event ID, exception name, and attempt count if available. Avoid logging sensitive payloads or entire messages unnecessarily. Metrics and alerts should catch abnormal retry spikes before consumer lag breaches operational thresholds.

Consumer-side retry is an intentional recovery mechanism: retry only errors capable of resolving on their own, cap attempt counts and wait durations, and route to recovery when progress is blocked. When error handlers, offsets, DLTs, and idempotent processing work together consistently, Spring Kafka streams can survive transient disruptions while keeping latency and duplicate risks under control.
