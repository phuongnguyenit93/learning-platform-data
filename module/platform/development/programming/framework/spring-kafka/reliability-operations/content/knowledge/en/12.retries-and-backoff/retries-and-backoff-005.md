# Maximum Deliveries

In Spring Kafka, a record can be received by a listener multiple times if processing fails and the error handler performs retries. When configuring retries, you must clearly define the maximum number of deliveries: how many times the listener is allowed to process the record initially, how many retry attempts occur, and where the record is recovered or routed once the limit is reached.

A common point of confusion is that some configurations count **the number of retries**, while others count **the total number of attempts including the first one**. With `DefaultErrorHandler` combined with `FixedBackOff`, the backoff's `maxAttempts` is the number of retries after the initial delivery. With Spring Kafka's retry topics, the `attempts` attribute represents the total number of attempts, including the initial processing attempt. Distinguish these two counting conventions before moving configurations to production.

## 1. Delivery, attempt, and retry

These terms are often used similarly but carry different meanings:

- **Delivery:** one instance where the consumer delivers a record to the listener for processing.
- **Attempt:** one try at processing a record. The initial processing run is also an attempt.
- **Retry:** an additional try after a previous attempt failed.
- **Recovery:** the action taken when no further retries will occur, such as sending the record to a dead-letter topic (DLT), recording the failure, or routing to a manual handling workflow.

If a listener receives a record once, fails, and is invoked three more times, the total number of deliveries is four: one initial attempt and three retries.

```text
Attempt 1: initial delivery -> failed
     |
     v
Attempt 2: retry 1 -> failed
     |
     v
Attempt 3: retry 2 -> failed
     |
     v
Attempt 4: retry 3 -> failed
     |
     v
Limit exhausted -> recovery / DLT
```

The maximum number of deliveries is a limit for one configured retry cycle. It does not equal the total number of times an event can appear across the entire system lifecycle: restarts, rebalances, manual replays, creating a new group ID, or an independent retry pipeline can all cause the record to be processed again at another time.

## 2. Maximum deliveries with DefaultErrorHandler and FixedBackOff

Spring Kafka's `DefaultErrorHandler` uses a `BackOff` to determine the retry count and wait interval between attempts. When using `FixedBackOff`, the constructor takes two arguments:

```java
new FixedBackOff(interval, maxAttempts)
```

Where:

| Parameter | Meaning |
|---|---|
| `interval` | Wait time between retry attempts, in milliseconds. |
| `maxAttempts` | Maximum number of retries after the initial delivery. |

Example:

```java
FixedBackOff backOff = new FixedBackOff(1_000L, 3L);
DefaultErrorHandler errorHandler = new DefaultErrorHandler(backOff);
```

The listener receives the initial delivery of the record. If that attempt fails, the handler allows up to three retries, spaced one second apart. If all attempts fail, the maximum number of times the listener can be invoked in this cycle is four.

| `maxAttempts` in FixedBackOff | Initial delivery | Maximum retries | Maximum total deliveries |
|---:|---:|---:|---:|
| 0 | 1 | 0 | 1 |
| 1 | 1 | 1 | 2 |
| 2 | 1 | 2 | 3 |
| 3 | 1 | 3 | 4 |
| 5 | 1 | 5 | 6 |

You can remember the formula:

```text
Maximum total deliveries = 1 + maximum number of retries
```

`maxAttempts=0` means no retries. Once the initial delivery fails, the handler immediately proceeds to configured recovery. This is appropriate for errors that cannot be resolved by retrying, or when failed records should go straight to a DLT.

## 3. Configuring DefaultErrorHandler with an explicit retry count

The following example allows one initial delivery and three retries, with a one-second wait interval:

```java
@Configuration
public class KafkaErrorConfiguration {

    @Bean
    public DefaultErrorHandler kafkaErrorHandler() {
        FixedBackOff backOff = new FixedBackOff(1_000L, 3L);
        return new DefaultErrorHandler(backOff);
    }
}
```

Attach the handler to the listener container factory:

```java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                DefaultErrorHandler kafkaErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
```

Listener processing the record:

```java
@KafkaListener(topics = "orders")
public void consume(OrderCreated event) {
    orderService.handle(event);
}
```

When `orderService.handle()` throws an exception, the container passes the error to `DefaultErrorHandler`. The handler uses the backoff to decide whether to retry. When backoff is exhausted, the recoverer is invoked. If no custom recoverer is passed, the handler still has default recovery behavior; in production, you must explicitly specify whether failed records are logged, skipped, or sent to a DLT according to application policy.

## 4. Attempt counts with Retry Topics

Spring Kafka also supports non-blocking retry via retry topics. Instead of holding the main consumer in an in-place retry cycle, the failed record is moved to a retry topic according to a backoff schedule. A listener on the retry topic tries processing again after the configured delay.

With `@RetryableTopic`, the `attempts` attribute is **the total number of attempts**, including the initial delivery. Example:

```java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 1_000, multiplier = 2.0),
    dltTopicSuffix = ".DLT"
)
@KafkaListener(topics = "orders", groupId = "order-service")
public void consume(OrderCreated event) {
    orderService.handle(event);
}
```

With `attempts = "4"`, the flow has at most four attempts: one on the main topic and up to three on the retry topics. Once attempts are exhausted and failures persist, the record is routed to the DLT per the retry topic configuration.

| `attempts` configuration | Initial delivery | Maximum retries | Maximum total attempts |
|---:|---:|---:|---:|
| `"1"` | 1 | 0 | 1 |
| `"2"` | 1 | 1 | 2 |
| `"3"` | 1 | 2 | 3 |
| `"4"` | 1 | 3 | 4 |
| `"5"` | 1 | 4 | 5 |

Because `attempts` is the total number of attempts, do not add an extra initial attempt when calculating retry topic configuration. This differs from `FixedBackOff.maxAttempts` in blocking retry.

## 5. Comparing counting between blocking retry and retry topics

Both mechanisms can limit how many times a listener tries to process a record, but their configuration and operational models differ:

| Mechanism | Counting attribute | Interpretation | Example total deliveries |
|---|---|---|---|
| `DefaultErrorHandler` + `FixedBackOff` | `maxAttempts` | Number of retries after the initial attempt. | `maxAttempts=3` -> 4 times. |
| `@RetryableTopic` | `attempts` | Total attempts, including the initial attempt. | `attempts="4"` -> 4 times. |

Do not copy a number directly from one mechanism to the other without converting its interpretation. If the business requirement is "at most four deliveries", you can configure `FixedBackOff(..., 3L)` or `@RetryableTopic(attempts = "4")`. Both configurations yield equivalent attempt counts, though retry timing, ordering, and error handling differ.

Blocking retry fits when you want fast retries within the same consumer flow and a small retry count. Non-blocking retry topics fit when longer delays are needed without holding the main consumer partition during the wait. Retry topics introduce extra topics, consumers, and orchestration; record order can change when a record moves to a retry topic and later returns for processing.

## 6. What happens after the final delivery?

Once the retry count is exhausted, the error handler needs a clear recovery action. Some options:

- Send the record to a DLT for investigation or later reprocessing.
- Log and persist error metadata in a tracking store.
- Route the record to a manual handling workflow.
- Skip the record only if the business permits it and that decision is recorded.

Example using `DeadLetterPublishingRecoverer` with `DefaultErrorHandler`:

```java
@Bean
public DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);
    FixedBackOff backOff = new FixedBackOff(1_000L, 3L);

    return new DefaultErrorHandler(recoverer, backOff);
}
```

After one initial delivery and three failed retries, the recoverer sends the record to the DLT according to routing rules. Under default configuration, the DLT topic name typically uses the `.DLT` suffix; the target topic must be created with appropriate partition count and serializers configured. If DLT publishing fails, recovery is incomplete and the handler must handle the recovery error per configuration.

With retry topics, a DLT handler can be declared:

```java
@DltHandler
public void handleDlt(OrderCreated event) {
    log.error("Order event exhausted retry attempts: eventId={}",
            event.eventId());
}
```

The DLT handler should record the event ID, original topic, partition, offset, exception, and processing timestamp for investigation. Do not merely log the payload and discard error traces. If replay is needed, have a process for selecting records, identifying root causes, and controlling duplicate processing.

## 7. Non-retryable exceptions reduce the number of deliveries

The maximum delivery count configured in backoff is an upper bound for retryable errors. `DefaultErrorHandler` can classify certain exceptions as non-retryable. When encountering such an error, the handler can skip remaining retries and go straight to the recoverer.

Example:

```java
@Bean
public DefaultErrorHandler kafkaErrorHandler() {
    FixedBackOff backOff = new FixedBackOff(1_000L, 3L);
    DefaultErrorHandler handler = new DefaultErrorHandler(backOff);

    handler.addNotRetryableExceptions(
            InvalidOrderException.class,
            UnsupportedCurrencyException.class);

    return handler;
}
```

In this configuration, `InvalidOrderException` and `UnsupportedCurrencyException` do not consume all three retries. They are routed to recovery according to the handler's policy. Other transient errors can use the configured backoff.

Classify according to the nature of the error:

- Timeouts or transient connection errors: typically retryable with a limit.
- Invalid data or missing required fields: rarely helpful to retry the same payload.
- Business rule violations: determine whether it is a transient state or a permanent error.
- Programming bugs: repeated retries usually only delay error detection.

When an exception is wrapped inside another exception, inspect the cause chain and configure the classifier appropriately. Misclassification can cause records to be retried too many times or sent to the DLT prematurely.

## 8. Maximum deliveries is not a global per-event limit

A retry limit typically applies to a single processing cycle coordinated by the error handler. It does not necessarily limit the total number of times an event is processed across all runs of the system.

Example with blocking retry:

1. The consumer receives the event and fails processing.
2. The error handler allows three retries after the initial attempt.
3. The process stops or the consumer rebalances before the cycle completes.
4. The partition is assigned to another member; the record may be re-read from the committed offset.
5. A new processing cycle can begin.

Therefore, the total number of listener invocations across the event's entire lifecycle can exceed `1 + maxAttempts`. Delivery counts also depend on offset commits, restarts, rebalances, and operational replays.

With retry topics, retry state is represented by the record moving across retry topics and associated headers. Nevertheless, manual replay, republishing a record, or creating a new retry stream can still make the event appear again. Do not use the retry count as a business deduplication key.

If a business requirement imposes an absolute limit on an event, persist attempt state durably by event ID in an appropriate store and define how to handle cases where that state is unavailable. That is a distinct business policy and cannot be replaced solely by the error handler's retry count.

## 9. Observing delivery counts via the delivery attempt header

With `DefaultErrorHandler`, Spring Kafka can populate the delivery count in the `KafkaHeaders.DELIVERY_ATTEMPT` header when `deliveryAttemptHeader` is enabled. This property is not enabled by default in standard handler configurations; verify the version in use.

Configuration example:

```java
@Bean
public DefaultErrorHandler kafkaErrorHandler() {
    DefaultErrorHandler handler =
            new DefaultErrorHandler(new FixedBackOff(1_000L, 3L));
    handler.setDeliveryAttemptHeader(true);
    return handler;
}
```

The listener can read the header:

```java
@KafkaListener(topics = "orders")
public void consume(
        OrderCreated event,
        @Header(name = KafkaHeaders.DELIVERY_ATTEMPT,
                required = false,
                defaultValue = "1") Integer deliveryAttempt) {

    log.info("Processing order event, deliveryAttempt={}", deliveryAttempt);
    orderService.handle(event);
}
```

The header value helps logs and metrics know which delivery attempt the listener is on in mechanisms that support it. The header is not an immutable global counter for the event. When a record is replayed or passes through a different mechanism, the count can change. To correlate end-to-end, also log the event ID and topic/partition/offset metadata.

## 10. Calculating total duration of maximum deliveries

The delivery limit directly affects how long a record can stay in retry. With fixed backoff:

```text
T_backoff = interval × number of retries
T_processing = total listener execution time across all attempts
T_total ≈ T_backoff + T_processing + T_overhead
```

Example:

```text
Maximum deliveries: 4
Duration per listener attempt: 800 ms
Wait interval: 1,000 ms
Retries: 3

T_processing = 4 × 800 ms = 3,200 ms
T_backoff = 3 × 1,000 ms = 3,000 ms
T_total ≈ 6,200 ms + overhead
```

This is the approximate duration when every attempt fails. If the dependency times out after 10 seconds on each attempt, actual duration will be much higher.

Blocking retry runs on the consumer processing thread and can delay the next `poll()`. When total processing and backoff time approaches `max.poll.interval.ms`, the consumer may be kicked out of the group and trigger a rebalance. Account for database/HTTP timeouts, batch size, and wait intervals—do not just multiply interval by retry count.

Retry topics can defer a record to another topic and let the main consumer continue processing other records. However, the time until the next attempt depends on the backoff schedule, the retry consumer's polling schedule, and the load on the retry topic. Configuring an attempt count does not equate to a completion SLA for the record.

## 11. Retries can cause duplicate processing

If a listener produces an external side effect and then fails before the offset is committed, the record can be redelivered. For example, the listener calls a payment API successfully, but the process stops before committing. The next delivery may call the API again.

Design idempotency keyed by event ID:

```java
@Transactional
public void handle(OrderCreated event) {
    if (processedEventRepository.existsByEventId(event.eventId())) {
        return;
    }

    orderRepository.createOrder(event);
    processedEventRepository.save(event.eventId());
}
```

In a real application, enforce a unique constraint on the event ID and save the marker in the same transaction as the business change to prevent race conditions. For external APIs, pass an idempotency key if the API supports it. Otherwise, design an appropriate reconciliation or outbox/inbox workflow.

Maximum deliveries limits the number of attempts within a retry policy, whereas idempotency protects the business against the same event being delivered multiple times. The two mechanisms serve different purposes.

## 12. Monitoring and alerting by delivery counts

To operate retries safely, monitor the following indicators:

- Total listener deliveries by topic and consumer group.
- Retry counts by exception type and listener endpoint.
- Number of records reaching the final delivery and moving to the DLT.
- Number of failed recoveries or failed DLT publishes.
- Delivery attempt distribution, especially the percentage of records requiring a second attempt or higher.
- Processing duration per attempt and total retry duration.
- Consumer lag, poll interval, and rebalance counts.

`DefaultErrorHandler`'s `RetryListener` can be used to observe failed deliveries:

```java
handler.setRetryListeners(new RetryListener() {
    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {

        log.warn("Delivery failed: topic={}, partition={}, offset={}, attempt={}",
                record.topic(),
                record.partition(),
                record.offset(),
                deliveryAttempt,
                exception);
    }
});
```

API signatures may differ across Spring Kafka versions; verify the dependency in use before implementing. Logs should include the event ID and exception type to aid tracing. Avoid logging full payloads if records contain sensitive data.

Set alerts when the retry rate spikes, the DLT grows rapidly, recovery fails, or lag increases alongside retries. If you only monitor listener failure counts without monitoring the DLT and lag, you can miss records being diverted from the main flow or consumers slowing down.

## 13. Common mistakes when configuring maximum deliveries

| Symptom | Possible cause | How to check |
|---|---|---|
| Listener is invoked more times than expected | Confusing `FixedBackOff`'s `maxAttempts` with total deliveries. | Compute `1 + maxAttempts`. |
| Retry topic has fewer attempts than expected | Mistaking `attempts` for retry count instead of total attempts. | Remember `@RetryableTopic(attempts=...)` includes the initial attempt. |
| Record goes to DLT immediately after the first failure | `maxAttempts=0`, `attempts="1"`, or non-retryable exception. | Check retry mechanism and exception classification. |
| Record is processed more times than configured limit | Restart, rebalance, or replay started a new delivery cycle. | Cross-check event ID, offset, committed offset, and deployment history. |
| Consumer rebalances during retries | Backoff and listener duration exceed the poll budget. | Calculate total processing time and adjust interval, retry count, or retry mechanism. |
| DLT grows rapidly | Dependency experiencing prolonged outage or delivery limit too low. | Analyze exceptions, recovery times, and recovery policy. |
| Business actions duplicated despite bounded retries | Non-idempotent listener or external API lacking an idempotency key. | Add deduplication keyed by event ID and reconcile transactions. |

## 14. Workflow for choosing delivery counts for a listener

When designing a retry policy, follow this sequence:

1. Identify which errors are recoverable and which should go straight to recovery.
2. Choose blocking retry or retry topics based on wait times, ordering, and tolerance for extra topics.
3. Decide whether the business requirement states total deliveries or additional retries.
4. For `FixedBackOff`, set `maxAttempts = desired total deliveries - 1`.
5. For `@RetryableTopic`, set `attempts` equal to the desired total attempts, including the initial attempt.
6. Calculate total processing and backoff time; verify against `max.poll.interval.ms` if using blocking retry.
7. Define the recoverer or DLT and how records are handled after the final attempt.
8. Design idempotent listeners to withstand restarts, rebalances, and replays.
9. Monitor delivery attempts, retry rates, DLT rates, recovery failures, and consumer lag post-deployment.

Maximum deliveries bounds the time and load a record can consume under a retry policy. By understanding each mechanism's counting rules, classifying exceptions sensibly, and defining recovery after the final attempt, Spring Kafka can handle transient errors while preserving the ability to investigate and recover unprocessable records.
