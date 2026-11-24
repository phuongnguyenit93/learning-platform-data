# FixedBackOff

In Spring Kafka, `FixedBackOff` is a backoff policy with a fixed interval between retry attempts. When a listener throws an exception, `DefaultErrorHandler` can use this policy to decide how long to wait before redelivering the record. If the retry attempts are exhausted, the error handler passes the record to a recoverer to log, send to a dead-letter topic, or perform another recovery action.

`FixedBackOff` belongs to Spring Framework (`org.springframework.util.backoff.FixedBackOff`), not a Kafka broker-specific setting. It describes the wait interval and retry count; `DefaultErrorHandler` uses that policy during listener container error handling.

## 1. What Problem Does FixedBackOff Solve?

A record can fail due to a transient cause, such as an overloaded database, a temporarily unresponsive HTTP service, or a dependency that just restarted. If the listener stops immediately on the first error, recoverable issues will disrupt processing.

Retry allows the application to try again after a wait period. `FixedBackOff` keeps that wait period constant between attempts:

```text
Listener receives record
       |
       v
   Processing error
       |
       v
   Wait 1 second
       |
       v
   Retry
       |
       v
   Processing error
       |
       v
   Wait 1 second
       |
       v
   Retry
       |
       v
 Retries exhausted? ---- No ----> continue retrying per policy
       |
      Yes
       |
       v
 Recoverer handles record
```

A fixed interval is suitable when the dependency typically recovers quickly and the expected wait time can remain steady. It is also easy to calculate total retry duration and simple to operate. For systems that need gradually increasing wait times to reduce pressure on a struggling dependency, exponential backoff may be more appropriate.

## 2. Structure and Attempt Counting

`FixedBackOff` has a primary constructor that takes two values:

```java
new FixedBackOff(interval, maxAttempts)
```

| Parameter | Meaning |
|---|---|
| `interval` | Wait time between retry attempts, in milliseconds. |
| `maxAttempts` | Maximum number of retries after the initial processing attempt. |

A common point of confusion is that `maxAttempts` is not the total number of times the listener is invoked. The initial record delivery is counted separately. For example:

```java
FixedBackOff backOff = new FixedBackOff(1_000L, 3L);
```

This means waiting 1,000 ms between retries and allowing up to three retries after the initial processing attempt. If all fail, the listener can be invoked up to four times in total:

| Invocation | Role | Next Action If Still Failing |
|---:|---|---|
| 1 | Initial processing attempt | Wait 1 second then retry 1. |
| 2 | Retry 1 | Wait 1 second then retry 2. |
| 3 | Retry 2 | Wait 1 second then retry 3. |
| 4 | Retry 3 | Retries exhausted; invoke recoverer. |

With three retries, the total backoff wait time when every attempt fails is about three seconds. Actual elapsed time also includes listener execution time, container coordination overhead, and dependency latency.

The default values of `FixedBackOff` in Spring Framework are typically represented by `DEFAULT_INTERVAL` and `DEFAULT_MAX_ATTEMPTS`. When configuring explicitly for an application, pass both parameters rather than relying on defaults.

## 3. Configuring FixedBackOff with DefaultErrorHandler

In Spring Kafka 2.8 and later, `DefaultErrorHandler` is the common error handler for listener containers. You can create a handler with a `FixedBackOff`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

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

With Spring Boot, the application may already have an auto-configured factory. In that case, configure the exact factory the listener uses or provide the bean according to the auto-configuration mechanism of your Spring Boot/Spring Kafka version. If multiple factories exist, do not assume the handler applies automatically to all of them.

Example listener:

```java
@KafkaListener(topics = "orders")
public void consume(OrderCreated event) {
    orderService.handle(event);
}
```

When `orderService.handle()` throws an exception, the container passes the error to `DefaultErrorHandler`. The handler uses `FixedBackOff` to control retry attempts. Once retries are exhausted, the recoverer is invoked as configured on the handler.

## 4. Configuring a Recoverer After Retries Are Exhausted

`FixedBackOff` only determines the wait interval and number of retries. It does not decide what to do with the record after retries are exhausted. That responsibility belongs to `DefaultErrorHandler`'s recoverer.

A recoverer can log and send failed records to a dead-letter topic (DLT). Example using `DeadLetterPublishingRecoverer`:

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

With the default `DeadLetterPublishingRecoverer` configuration, records are typically sent to a topic with the `.DLT` suffix while preserving the corresponding partition. You must create an appropriate destination topic, ensure it has enough partitions, and configure compatible serializers/deserializers. Routing rules can be customized when constructing the recoverer.

Processing flow:

```text
Record from topic orders
        |
        v
Listener fails
        |
        v
FixedBackOff: max 3 retries, wait 1 second
        |
        v
Retries exhausted
        |
        v
DeadLetterPublishingRecoverer
        |
        v
orders.DLT
```

If the recoverer also fails, the record has not been successfully recovered. `DefaultErrorHandler` has mechanisms for handling recovery failures; understand how backoff reset works when recovery fails and ensure the DLT producer can publish data. Do not treat exhausting retries as synonymous with the record having been safely handled.

## 5. Distinguishing Retries from Total Deliveries

When designing a policy, explicitly document both the retry count and the total number of times the listener may receive a record. The table below illustrates several configurations:

| FixedBackOff | Initial Attempt | Max Retries | Max Total Calls When All Fail |
|---|---:|---:|---:|
| `new FixedBackOff(500L, 0L)` | 1 | 0 | 1 |
| `new FixedBackOff(1_000L, 1L)` | 1 | 1 | 2 |
| `new FixedBackOff(1_000L, 3L)` | 1 | 3 | 4 |
| `new FixedBackOff(2_000L, 5L)` | 1 | 5 | 6 |

`maxAttempts=0` means no retries. After the initial processing attempt fails, the handler can invoke the recoverer immediately. This configuration is useful when errors cannot be resolved by retrying or when you want to send records straight to the DLT.

Do not confuse retry count with `max.poll.records`. `max.poll.records` limits the number of records returned in a single poll; `FixedBackOff.maxAttempts` limits the number of retries for a single failed record processing cycle. The two properties control different aspects of the consumer.

## 6. Choosing the Wait Interval and Retry Count

The wait interval should match the dependency's recovery time and the consumer's processing time limits. For example, if a database typically recovers within a few seconds after a failover, retrying one second apart may suffice. If a downstream service needs longer to recover, overly frequent retries will generate extra load and error logs.

You can estimate the maximum wait time:

```text
T_backoff = interval × maxAttempts
```

Example:

```text
interval = 2.000 ms
maxAttempts = 4
T_backoff = 2.000 × 4 = 8.000 ms
```

The total time a record stays in the processing cycle also includes the execution time of each listener invocation:

```text
T_total ≈ (initial + maxAttempts) × T_processing
          + maxAttempts × interval
          + T_overhead
```

This is an estimate for sequential retries with roughly similar execution times across attempts. In practice, each attempt's duration can vary significantly.

If retries run synchronously on the consumer thread, total retry time also counts toward the interval between two `poll()` calls. When `T_total` approaches or exceeds `max.poll.interval.ms`, the consumer may be evicted from the group and trigger a rebalance. Coordinate backoff policy with `max.poll.interval.ms`, batch size, and dependency timeouts.

## 7. FixedBackOff Is Not Exponential Backoff

`FixedBackOff` always waits the same amount of time between retries. For instance, `new FixedBackOff(2_000L, 4L)` creates four wait intervals of two seconds each.

```text
Failure 1 --2s--> Retry 1
Retry 1   --2s--> Retry 2
Retry 2   --2s--> Retry 3
Retry 3   --2s--> Retry 4
```

Exponential backoff increases the wait time after each failure—for example, 1 second, 2 seconds, 4 seconds, 8 seconds. This reduces the call rate to a dependency during prolonged outages. Spring Kafka offers other backoff options, such as `ExponentialBackOffWithMaxRetries`, which can be used with `DefaultErrorHandler` when gradually increasing intervals are needed.

| Criterion | Fixed Backoff | Exponential Backoff |
|---|---|---|
| Wait interval | Constant across retries. | Increases by a multiplier. |
| Time calculation | Predictable and simple. | Requires summing the interval series and maximum cap. |
| Load on dependency | Can generate steady retry load during long outages. | Reduces retry frequency over time. |
| Best suited for | Short errors with relatively stable recovery times. | Dependencies that may need long or uncertain recovery times. |

Do not choose a backoff strategy just because one looks more sophisticated. Base the decision on error characteristics, latency limits, and the target system's recovery capacity.

## 8. Classifying Exceptions Before Retrying

Not every exception can be fixed by waiting and retrying. For example, a temporary database connection error can be retried; invalid data or a business-rule violation will usually fail repeatedly if the same record is reprocessed multiple times.

`DefaultErrorHandler` supports exception classification. You can declare non-retryable exceptions:

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

For these errors, the handler skips retries and proceeds directly to the configured recoverer. You can also add retryable exceptions when you need to adjust the default classification. Inspect the entire cause chain and how exceptions are wrapped by the framework; classifying only by the outermost exception may not reflect the root cause.

A practical rule of thumb:

- Transient errors: consider bounded retries, such as timeouts, connection errors, or temporarily unavailable services.
- Data/validation errors: usually route directly to the recoverer or DLT for investigation.
- Programming bugs: fix the code; continuous retries usually only delay error detection.
- Unknown errors: use a small retry count, log sufficient context, and have a clear recovery mechanism.

## 9. Bounded Retries and Idempotent Processing

Retrying means the listener can be invoked multiple times for the same record. If the listener performs a non-idempotent operation, retries can create duplicate effects. For example, if the listener adds 100 reward points and fails before committing the offset, a retry could add another 100 points.

Design business logic to tolerate receiving the same event multiple times:

```java
@Transactional
public void applyReward(RewardRequested event) {
    if (processedEventRepository.existsByEventId(event.eventId())) {
        return;
    }

    accountRepository.addPoints(event.accountId(), event.points());
    processedEventRepository.save(event.eventId());
}
```

The example above requires a unique constraint on `eventId`, and saving the marker must be in the same transaction as the points update. Checking `exists` alone without a unique constraint can suffer from race conditions under concurrent processing. For high-reliability systems, use a unique constraint or an atomic inbox mechanism.

Do not rely on `FixedBackOff` to achieve exactly-once processing. Backoff only decides when to retry; idempotency and transactional mechanisms protect business effects when records are delivered multiple times.

## 10. Impact on Offsets and Consumer Groups

When a listener throws an exception, `DefaultErrorHandler` decides whether to retry or recover the record. With a record listener, the container can seek to re-read the failed record and remaining records according to the error-handling strategy. The offset is only advanced per the acknowledgment/commit policy after processing or recovery is considered complete.

While retries are not exhausted, the failed record still needs reprocessing. If the application stops during backoff or a group rebalance occurs, the record may be redelivered to another member. Therefore, the actual number of attempts across the entire lifecycle can be affected by restarts and reprocessing after rebalances; `maxAttempts` is not a permanent global limit for an event across all application runs.

When the recoverer successfully handles a record after retries are exhausted, the handler can treat the record as recovered and allow consumer progress to continue according to configuration. If the recoverer fails, the record may be redelivered and recovery retried according to the handler's behavior/configuration. Do not commit the offset before critical recovery completes.

For a batch listener, identifying the failing record and which portion of the batch needs retrying differs from a record listener. If the batch listener throws `BatchListenerFailedException` with the failing record's index, `DefaultErrorHandler` can handle the preceding records and retry from the failing record. If the failing record is not identified, the handler may apply whole-batch retry. Choose how exceptions are thrown to match the batch listener contract.

## 11. Monitoring Retries and Backoff

To operate a `FixedBackOff` policy, you need visibility into which records are retrying, attempt counts, wait times, and recovery outcomes. You can configure a `RetryListener` to receive notifications on retries or recovery:

```java
handler.setRetryListeners(new RetryListener() {
    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {

        log.warn("Kafka delivery failed: topic={}, partition={}, offset={}, attempt={}",
                record.topic(),
                record.partition(),
                record.offset(),
                deliveryAttempt,
                exception);
    }
});
```

Callback signatures can vary across Spring Kafka versions; check the API of the version you are using when implementing. Corresponding recovery callbacks can be used to record when a record was recovered or when recovery failed.

Recommended metrics to track:

- Listener failure counts by exception type.
- Retry counts and delivery attempt distribution.
- Total retry/backoff time.
- Counts of records recovered or sent to the DLT.
- DLT publish failure counts.
- Consumer lag and listener processing duration.
- Rebalances or poll timeouts occurring during retries.

Do not log full payloads if they contain personal or confidential data. Topic, partition, offset, event ID, and exception type are usually enough to correlate retry events with business logs.

## 12. Common Errors When Using FixedBackOff

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Listener invoked more times than expected | `maxAttempts` is the number of retries after the initial attempt, not total calls. | Compute max total calls as `1 + maxAttempts`. |
| Record sent to DLT immediately | `maxAttempts=0`, exception classified as non-retryable, or handler not using the expected backoff. | Check `FixedBackOff`, exception classification, and factory. |
| Retries happen too fast | `interval` is too small or zero. | Increase interval to match realistic recovery time and avoid burst retries. |
| Consumer rebalances during retries | Total processing and backoff time exceeds `max.poll.interval.ms`. | Calculate total retry time, reduce attempts, or use an appropriate backoff strategy. |
| DLT does not receive records | Recoverer or DLT producer failing; destination topic/serializer incompatible. | Check producer, write permissions, DLT topic, and recovery errors. |
| Business logic duplicated after retry | Listener is not idempotent or record redelivered after crash. | Use event ID, unique constraint, or inbox/outbox. |
| Data exceptions retried repeatedly | Non-retryable errors not classified. | Add `addNotRetryableExceptions` and route errors to recovery. |
| Batch reprocessed multiple times | Handler cannot identify the failing record in the batch. | Use `BatchListenerFailedException` where appropriate and understand batch retry behavior. |

## 13. Process for Choosing FixedBackOff for a Listener

When designing retries for a new listener, you can follow this sequence:

1. List potential exceptions and classify transient errors, data errors, and programming bugs.
2. Measure typical dependency recovery time and pick an appropriate fixed interval.
3. Choose the maximum retry count based on business latency and poll interval limits.
4. Calculate total listener invocations as one initial attempt plus the retry count.
5. Choose a recoverer after retries are exhausted: log, DLT, or manual handling workflow.
6. Ensure the recoverer can persist data reliably and has separate failure monitoring.
7. Design the listener to be idempotent to withstand retries, restarts, and rebalances.
8. Measure retry rate, recovery rate, lag, and processing time after deployment.

`FixedBackOff` provides a simple, predictable retry policy for `DefaultErrorHandler`. When configured with the right retry count, wait interval, exception classification, and recoverer, consumers can handle transient errors in a controlled way and route unprocessable records into a clear recovery workflow.
