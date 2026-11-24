# BackOff in Error Handlers

## 1. What Problem Does BackOff Solve?

When a listener processes a Kafka record and throws an exception, Spring Kafka can retry processing that record. If it retries immediately and continuously, the application generates heavy load against a struggling database, API, or broker. If it waits too long, consumer lag and business latency grow.

**BackOff** defines the wait duration between retry attempts and when to stop retrying. It helps the error handler pace retry attempts, give dependent systems time to recover, and cap how many times a record is attempted before transitioning to recovery.

In Spring Kafka, `DefaultErrorHandler` uses Spring Framework's `BackOff` abstraction. The error handler coordinates three parts:

- **Listener:** processes the record and may throw an exception.
- **BackOff:** decides how long to wait before the next attempt and when retries are exhausted.
- **Recoverer:** takes action when retries stop, such as publishing the record to a Dead Letter Topic (DLT), saving it to quarantine, or persisting the failure durably.

```text
Kafka record
    |
    v
Listener processes
    |
    +---- success -------------------------> container continues/commits per configuration
    |
    +---- throws exception
              |
              v
       DefaultErrorHandler
              |
              v
          BackOff
          /     \
  retries left  retries exhausted (STOP)
       |             |
       v             v
  wait delay      Recoverer
       |             |
       v             +---- DLT / error store / recovery
  invoke listener again
```

BackOff only controls wait schedules and retry limits. It does not fix bad data, does not guarantee a dependency will recover, and does not provide exactly-once semantics by itself.

## 2. BackOff and BackOffExecution

Spring Framework defines two core interfaces in the `org.springframework.util.backoff` package:

- `BackOff`: creates a new retry schedule execution via `start()`.
- `BackOffExecution`: maintains state for that execution and returns the next wait interval via `nextBackOff()`.

`nextBackOff()` returns the number of milliseconds to wait before the next retry. When the retry schedule is complete, it returns `BackOffExecution.STOP` (the sentinel value `-1`). The error handler uses this signal to stop retrying and invoke the recoverer.

Each failed record processing flow gets its own BackOff progression. Never manually share a single `BackOffExecution` across multiple records, as retry attempt counts would be mixed together. Pass a `BackOff` capable of creating a fresh execution for each processing cycle.

Basic flow:

1. The listener processes the record for the first time.
2. The listener throws an exception.
3. The error handler starts or advances the record's `BackOffExecution`.
4. If `nextBackOff()` returns a delay, the error handler waits and retries per container policy.
5. If `nextBackOff()` returns `STOP`, the error handler invokes the recoverer.
6. If recovery succeeds, the container proceeds according to its commit/seek mechanism; if recovery fails, the recovery error is handled per error handler configuration.

## 3. FixedBackOff: Constant Wait Interval

`FixedBackOff` is the simplest option. It uses the same wait interval between retries and a fixed maximum number of retries.

```java
import org.springframework.util.backoff.FixedBackOff;

var backOff = new FixedBackOff(1_000L, 2L);
```

The two parameters are:

- `interval`: wait time between retries, in milliseconds.
- `maxAttempts`: number of retries after the initial processing attempt.

With `new FixedBackOff(1_000L, 2L)`, the listener is invoked at most three times if all three attempts fail:

| Invocation | Outcome | Next Action |
|---:|---|---|
| 1 | Initial attempt fails | Wait 1 second |
| 2 | Retry 1 fails | Wait 1 second |
| 3 | Retry 2 fails | BackOff terminates, invoke recoverer |

`maxAttempts` in `FixedBackOff` is the number of retries, not the total number of listener invocations. This is a common point of confusion when reading configurations.

### No-Retry Example

```java
var noRetry = new FixedBackOff(0L, 0L);
```

When the initial attempt fails, processing goes straight to the recoverer. This fits data errors that cannot be resolved by retrying, provided the recoverer takes action to preserve the record.

### Many Retries with Short Wait Example

```java
var shortRetry = new FixedBackOff(250L, 4L);
```

The listener can be called up to five times: the initial attempt plus four retries, spaced 250 ms apart. This can work for brief infrastructure glitches, but is unsuitable for outages lasting several minutes.

Do not use very large retry counts with a 0 interval for errors that cannot self-heal. That can create a tight hot loop, consume CPU, and stall the consumer group.

## 4. Configuring FixedBackOff with DefaultErrorHandler

The following example configures two retries spaced one second apart, then publishes the failed record to a DLT:

```java
@Configuration
public class KafkaErrorHandlerConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> dltTemplate) {

        ConsumerRecordRecoverer recoverer =
                new DeadLetterPublishingRecoverer(dltTemplate);

        BackOff backOff = new FixedBackOff(1_000L, 2L);
        return new DefaultErrorHandler(recoverer, backOff);
    }
}
```

Attach the error handler to the listener container factory:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultErrorHandler kafkaErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
```

Listener:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "ordersListenerFactory")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
```

When `orderService.process()` throws an exception, `DefaultErrorHandler` applies the BackOff. Once retries are exhausted, `DeadLetterPublishingRecoverer` sends the record to the DLT using the default or application-configured destination resolver.

In a real application, the DLT template must be able to serialize the failing record's key/value and headers. If the consumer uses `ErrorHandlingDeserializer` and the record holds raw `byte[]`, configure the DLT serializer to support both byte arrays and normal payloads.

## 5. Exponential BackOff: Gradually Increasing Wait Time

For dependency failures that may need longer to recover, a fixed interval can trigger bursts of retry requests. Exponential backoff increases the wait duration after each failure.

Example schedule with an initial interval of 500 ms, multiplier 2, and max interval 5 seconds:

| Retry Attempt | Expected Wait Time |
|---:|---:|
| 1 | 500 ms |
| 2 | 1,000 ms |
| 3 | 2,000 ms |
| 4 | 4,000 ms |
| 5 onward | 5,000 ms (max interval reached) |

You can configure Spring Framework's `ExponentialBackOff`:

```java
import org.springframework.util.backoff.ExponentialBackOff;

ExponentialBackOff backOff = new ExponentialBackOff();
backOff.setInitialInterval(500L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(5_000L);
backOff.setMaxElapsedTime(20_000L);
```

`maxInterval` caps the wait time for any single retry. `maxElapsedTime` caps the total execution time of the BackOff schedule; once reached, the execution may return `STOP` even if retries have not hit a fixed attempt count.

Unlike `FixedBackOff`, the retry count of exponential backoff can be governed by total elapsed time and interval parameters. Test the actual schedule if you require an exact cap on invocation counts.

Do not confuse `org.springframework.util.backoff.BackOff` with Spring Retry's `BackOffPolicy`. Those are two different abstractions. Spring Kafka's `DefaultErrorHandler` accepts Spring Framework's `BackOff`.

## 6. Choosing BackOff by Error Category

Not all errors should be retried identically. A typical policy divides errors into three categories:

| Error Category | Examples | Typically Suitable Policy |
|---|---|---|
| Transient error | Database timeout, brief network glitch, dependent service temporarily unavailable | Bounded retries with fixed or exponential backoff |
| Unrecoverable data error | Malformed JSON, payload missing required field, invalid type header | Do not retry or retry minimally; forward to DLT/quarantine for investigation |
| Business error needing intervention | Order state forbids transition, account locked | Classify by business rule; DLT, wait for another event, or handle manually |

Retrying an unrecoverable data error simply reads the exact same bytes and raises the exact same exception. Waiting longer will not make the record valid.

### Classifying Exceptions in DefaultErrorHandler

`DefaultErrorHandler` can classify retryable and non-retryable exceptions. Example:

```java
DefaultErrorHandler handler = new DefaultErrorHandler(
        new DeadLetterPublishingRecoverer(dltTemplate),
        new FixedBackOff(1_000L, 3L));

handler.addNotRetryableExceptions(
        InvalidOrderPayloadException.class,
        UnsupportedEventVersionException.class);

handler.addRetryableExceptions(
        TemporaryInventoryUnavailableException.class);
```

Non-retryable exceptions skip the retry schedule and go straight to recovery. Retryable exceptions use the configured BackOff. Inspect the actual exception thrown by the listener or deserializer; exceptions may be wrapped inside another exception.

Spring Kafka also maintains a default classification list. Read the documentation for your exact version and only add the classifications you need, avoiding inadvertently turning data errors into retryable ones or infrastructure failures into non-retryable ones.

## 7. Custom BackOff

When a specialized schedule is required, you can implement `BackOff` and `BackOffExecution`. The example below waits 500 ms, then 2 seconds, then stops:

```java
BackOff customBackOff = () -> new BackOffExecution() {
    private int attempt;

    @Override
    public long nextBackOff() {
        return switch (attempt++) {
            case 0 -> 500L;
            case 1 -> 2_000L;
            default -> BackOffExecution.STOP;
        };
    }
};

DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, customBackOff);
```

This schedule permits two retries after the initial attempt. Every call to `start()` creates a new execution with its own counter. This matters when multiple partitions experience failing records concurrently.

Custom BackOff is useful when:

- Wait intervals must vary by exception type.
- You want to bound by total duration rather than attempt count.
- You need an irregular delay sequence matching a dependent system's SLA.
- You want to integrate a retry schedule computed from business configuration.

Keep BackOff logic pure and easy to test. Never call a database, HTTP service, or Kafka broker inside `nextBackOff()`; this method runs on the retry control path and must return quickly and deterministically.

## 8. BackOff Handler: How Is the Wait Performed?

BackOff decides **how long to wait**; `BackOffHandler` decides **how that wait is executed**.

In `DefaultErrorHandler`, the default is waiting on the consumer thread. For short delays, this is straightforward. However, if the delay is long, the consumer thread may fail to call `poll()` within `max.poll.interval.ms`, causing the member to be kicked out of the group and triggering a rebalance.

Spring Kafka provides `ContainerPausingBackOffHandler` to pause the listener container during backoff instead of merely sleeping on the consumer thread. The container can continue performing the polls needed to preserve group membership; actual wait precision depends on `pollTimeout` and container scheduling.

Example:

```java
DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(60_000L, 2L),
        new ContainerPausingBackOffHandler());
```

This example requests a one-minute delay between retries and uses the container-pausing handler. For long backoffs, this is usually a better choice than sleeping the consumer thread. Verify behavior with your specific Spring Kafka version and container configuration.

### When to Use Each Approach?

| Wait Mechanism | Best For | Caveats |
|---|---|---|
| Default sleep-based handler | Short delays, fast processing, no risk of hitting `max.poll.interval.ms` | Blocks the consumer thread while waiting |
| `ContainerPausingBackOffHandler` | Long delays where container/group liveness must be preserved during waits | Actual delay can drift based on poll timeout; pausing stops the partition from processing new records during that time |

Do not choose container pausing expecting the consumer to keep processing subsequent records in the same partition. Its purpose is to preserve container/group lifecycle while waiting to retry; a paused partition does not continue normal main-flow processing.

## 9. BackOff and max.poll.interval.ms

A Kafka consumer must call `poll()` regularly within the `max.poll.interval.ms` bound. If processing a batch plus retry/backoff time exceeds this limit, the consumer can be treated as stalled and removed from the group.

Example:

- `max.poll.interval.ms = 300000` (5 minutes).
- The listener takes 90 seconds to process a batch.
- BackOff waits 4 minutes before retrying.
- Total time without polling can exceed 5 minutes.

A rebalance can then occur. Partitions are reassigned to another consumer and uncommitted records may be redelivered. Therefore, when designing backoff, account for listener processing time, batch size, retry count, and wait intervals together.

Mitigations:

1. Reduce per-record/batch processing time by optimizing business logic.
2. Lower `max.poll.records` if a polled batch is too large, while evaluating throughput.
3. Choose shorter backoffs if SLAs and error types allow.
4. Use `ContainerPausingBackOffHandler` for long delays.
5. Consider retry topics/non-blocking retries if you do not want to stall the main partition and business rules tolerate ordering changes.

Do not simply raise `max.poll.interval.ms` to mask overly long retries. Weigh failover time, rebalance behavior, duplicate processing, and the maximum latency acceptable to the business.

## 10. Blocking Retry vs. Non-Blocking Retry

BackOff in `DefaultErrorHandler` is typically used for blocking retries: the failing record is retried on the partition's processing path. While waiting and retrying, subsequent records in that partition do not bypass the failing record in normal processing.

`@RetryableTopic` is a different mechanism: Spring Kafka forwards the failing record to a retry topic with a matching delay, and a retry topic consumer attempts it later. The main topic consumer can move on to the next record.

| Criterion | Blocking Retry with DefaultErrorHandler | Non-Blocking Retry Topic |
|---|---|---|
| Where wait happens | On the consumer/container thread handling the failing record | On a retry topic and forwarding schedule |
| Subsequent records in main partition | Typically blocked behind the failing record | Can proceed ahead of the record being retried |
| Ordering | Easier to preserve per-partition ordering | Newer events can finish before the failing event |
| Best suited for | Ordering required or only short waits needed | Main flow must continue and asynchronous retries are acceptable |
| BackOff | Error handler's `BackOff`/`BackOffHandler` | Retry topic backoff configuration, e.g., via `@RetryableTopic` |

Avoid configuring both mechanisms as if they form a single unified retry schedule. Define clearly which retries happen inside the listener container and which are offloaded to separate topics. In particular, if events with the same aggregate/key require strict ordering, non-blocking retries can invert business order.

## 11. BackOff with Batch Listeners

For a batch listener, the error handler needs to know the scope of the failure. If the listener throws `BatchListenerFailedException` identifying the failing record or index, `DefaultErrorHandler` can retry starting from the failing record under the configured policy instead of always reprocessing the entire batch.

If a batch listener throws a generic exception without identifying the failing record, the error handler may have to retry the whole batch. In that case, BackOff applies to re-executing the batch.

Example:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "batchListenerFactory")
public void onOrders(List<ConsumerRecord<String, OrderCreated>> records) {
    for (int index = 0; index < records.size(); index++) {
        try {
            orderService.process(records.get(index).value());
        } catch (Exception exception) {
            throw new BatchListenerFailedException(
                    "Cannot process order record", exception, index);
        }
    }
}
```

With this pattern, the error handler knows the failing record's index. Verify offset, retry, and recovery behavior when a batch spans multiple partitions, since offsets remain independent per partition. If the listener performs a bulk database operation that cannot pinpoint a single failing record, design transactions or a validation step so failures can be isolated.

## 12. BackOff in Transactional Listeners

When a listener container uses Kafka transactions, an exception from the listener normally rolls back the transaction. In this model, post-rollback retries are typically managed by `AfterRollbackProcessor` (defaulting to `DefaultAfterRollbackProcessor`); do not copy a non-transactional `DefaultErrorHandler` setup verbatim.

`DefaultAfterRollbackProcessor` also supports `BackOff` and a recoverer to decide how many times to reprocess after rollback and what to do once retries are exhausted. You can therefore use the same `FixedBackOff` or exponential backoff concepts, configured on the after-rollback processor.

Key distinctions:

- For non-transactional listeners, `DefaultErrorHandler` drives retries and recovery.
- For transactional listeners, exceptions roll back the transaction; `AfterRollbackProcessor` drives seeks, retries, and recovery after rollback.
- BackOff does not make side effects outside Kafka transactional.
- If a database committed before the Kafka transaction rolled back, the record may be reprocessed; idempotency or appropriate transaction coordination is required.

Never assume Kafka transactions plus BackOff automatically provide exactly-once guarantees for databases, HTTP calls, or emails.

## 13. Recovery After BackOff Completes

When BackOff returns `STOP`, the error handler invokes the recoverer. The recoverer can:

- Publish the record to a DLT using `DeadLetterPublishingRecoverer`.
- Save the payload and metadata to a quarantine table.
- Send an operational alert or create a ticket through another mechanism.
- Mark the record unprocessable and allow the group to advance.

Recovery must be durable. If a recoverer merely logs the error and returns, the container may treat the record as recovered and advance progress; if logs are insufficient to restore the data, the record can be lost from the business workflow.

DLT example:

```java
ConsumerRecordRecoverer recoverer =
        new DeadLetterPublishingRecoverer(dltTemplate);

DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(2_000L, 3L));
```

With this setup, the listener is invoked up to four times: the initial attempt plus three retries. After the final failure, the recoverer publishes the record to the DLT. Verify publish outcomes and configure serializers, topics, partition mapping, and ACLs so recovery does not fail.

If the recoverer throws an exception, recovery is not complete. `DefaultErrorHandler` has a policy for resetting BackOff when recovery fails; exact behavior is configurable and should be verified for your version. Do not assume a record is handled merely because the recoverer was called.

## 14. Monitoring BackOff Effectiveness

BackOff effectiveness should be evaluated using operational metrics, not just code configuration. Monitor:

- Listener failure counts and retry counts by exception class.
- Actual wait durations between retry attempts.
- Records that exhausted retries and were recovered.
- DLT publish success and failure rates.
- Consumer lag by partition and time records spend in retry state.
- Rebalance counts during prolonged retries.
- p95/p99 record processing times and dependency recovery times.

Logs should include `eventId`, topic, partition, offset, exception class, retry attempt, and recovery destination. Do not log full sensitive payloads just to observe retries.

If retry rates spike suddenly, inspect dependency health and exception types. Automatically increasing retry counts or shortening delays can worsen overload on a struggling dependency.

## 15. Testing BackOff

Tests must verify listener invocation counts, wait intervals, recovery, and post-restart behavior:

1. **FixedBackOff:** configure 2 retries and verify the listener is called up to 3 times before the recoverer.
2. **No retry:** configure `FixedBackOff(0, 0)` and verify the recoverer is invoked immediately after the initial failure.
3. **ExponentialBackOff:** verify delay sequences scale according to initial interval, multiplier, and max interval.
4. **Exception classification:** verify non-retryable exceptions go straight to recovery while retryable exceptions use BackOff.
5. **Recoverer succeeds:** verify the record is routed to the DLT or persisted to quarantine and the consumer advances per policy.
6. **Recoverer fails:** verify the record is not falsely marked recovered and BackOff/error handler behave as configured.
7. **Long backoff:** compare the sleep-based handler and `ContainerPausingBackOffHandler`; watch `max.poll.interval.ms` and rebalances.
8. **Batch listener:** verify `BatchListenerFailedException` identifies the failing record and retries the right scope.
9. **Transactional listener:** verify rollbacks and that `AfterRollbackProcessor` applies BackOff as intended.
10. **Redelivery/idempotency:** stop the application mid-retry and verify side effects are not unexpectedly duplicated.

You can use `spring-kafka-test` or the matching Spring Boot Kafka test starter. For timing tests, use short, controlled BackOffs; avoid making the test suite depend on unnecessarily long delays. Rebalance and broker failure scenarios need integration tests close to production conditions.

## 16. Common Pitfalls When Configuring BackOff

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Listener called more times than expected | Confusing `maxAttempts` with total invocations instead of retry count | Add the initial attempt when calculating total calls |
| Retries fire continuously | Interval is 0 or too short | Set an appropriate delay, use exponential backoff, and cap retries |
| Consumer rebalances during long retries | Consumer thread fails to poll during backoff and exceeds `max.poll.interval.ms` | Use `ContainerPausingBackOffHandler`, reduce processing time, or adjust poll strategy |
| Invalid data record retried forever | Non-retryable exceptions not classified or unbounded retry policy | Classify errors and configure a recoverer/DLT |
| No records in DLT | Wrong recoverer/template/topic/serializer/ACL or publish failed | Check publish result, serializer, and destination |
| Subsequent unrelated records delayed | Blocking retry holds the partition on the failing record | Consider retry topics if business rules allow ordering changes |
| Entire batch retried | Listener does not identify the failing record | Throw `BatchListenerFailedException` with the appropriate index/record |
| Transaction rolls back without DefaultErrorHandler retrying | Transactional container uses `AfterRollbackProcessor` | Configure BackOff on `DefaultAfterRollbackProcessor` |
| Raising retries makes the system worse | Dependency is overloaded and retries add extra load | Reduce retry pressure, use longer backoffs, cap concurrency, and restore the dependency |

## 17. Workflow for Choosing BackOff

1. Identify exception types and whether they can self-heal.
2. Decide retryable vs. non-retryable for each exception group.
3. Cap retry counts or total retry duration based on SLAs.
4. Choose fixed backoff for short, predictable errors; exponential backoff for outages needing longer recovery.
5. For long delays, choose `ContainerPausingBackOffHandler` and evaluate `max.poll.interval.ms`.
6. Choose the recoverer once BackOff terminates: DLT, quarantine, or manual handling.
7. If using a batch listener, identify the failing record; if using transactions, configure `AfterRollbackProcessor`.
8. Test retry counts, delays, recovery failures, rebalances, and idempotency.
9. Monitor retry rates, lag, recoveries, and dependency health post-deployment.

Do not pick retry counts by guesswork. Base them on real dependency recovery times, how long a record is allowed to remain in flight, retention windows, and capacity to drain backlogs once the service recovers.

## 18. Summary

- BackOff controls wait intervals between retries and when to stop; the recoverer decides what happens after retries are exhausted.
- `BackOff` creates a `BackOffExecution`; `nextBackOff()` returns a delay or `STOP`.
- `FixedBackOff(interval, maxAttempts)` uses a constant interval; `maxAttempts` is the number of retries after the initial processing attempt.
- `ExponentialBackOff` increases delays progressively and can cap max interval and total elapsed time.
- `DefaultErrorHandler` combines BackOff with retries/recovery for non-transactional listeners.
- `BackOffHandler` governs how the wait happens; `ContainerPausingBackOffHandler` helps with long delays to avoid blocking the consumer thread too long.
- Blocking retries keep the failing record on the partition flow; retry topics allow later records to move ahead.
- Batch listeners should identify the failing record whenever possible; transactional listeners typically use `AfterRollbackProcessor`.
- Recovery must be durable; retries and BackOff do not replace idempotency or exactly-once semantics.

When you choose the right BackOff for each error type and SLA, Spring Kafka can retry predictably, avoid overloading dependencies, and route unrecoverable records to a separate workflow so the consumer group keeps moving.

## References

- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka API — DefaultErrorHandler](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/DefaultErrorHandler.html)
- [Spring Framework API — BackOff](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/util/backoff/BackOff.html)
- [Spring Framework API — ExponentialBackOff](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/util/backoff/ExponentialBackOff.html)
