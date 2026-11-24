# Exponential Backoff

When a Kafka listener encounters a transient error, retrying immediately many times often makes the situation worse. If a database, HTTP service, or broker is overloaded, rapid consecutive calls keep applying pressure directly to the struggling dependency. **Exponential backoff** solves this problem by increasing the wait time between retry attempts.

In Spring Kafka, backoff can be used with the listener container's blocking retry mechanism, typically via `DefaultErrorHandler`, or with non-blocking retry topics via `@RetryableTopic`. The two models operate differently: blocking retry keeps the record in the current processing flow, whereas retry topics move the record to a delayed topic so the consumer can continue with other work.

## 1. Why is backoff needed?

Suppose a listener receives an order event and calls an inventory-check service. That service may temporarily return timeouts because it is being deployed or is under heavy load. If the listener retries immediately, many consumers may resend requests continuously at the same time, making it even harder for the service to recover.

Backoff creates a pause between attempts:

```text
Attempt 1: failed
     |
     +---- wait 1 second ---> Attempt 2: failed
                                |
                                +---- wait 2 seconds ---> Attempt 3: failed
                                                            |
                                                            +---- wait 4 seconds ---> Attempt 4
```

Progressively increasing wait intervals helps:

- Reduce the rate of repeated requests while a dependency is failing.
- Give the dependent system time to recover.
- Avoid wasting CPU and network resources on overly frequent retries.
- Bound the number of attempts and processing time per record.
- Distinguish transient errors from data or business errors that cannot self-recover.

Backoff does not make a failing operation succeed. It only regulates when retries happen. If the root cause is invalid data or a business rule violation, waiting longer will not fix the problem.

## 2. Fixed backoff vs. exponential backoff

With **fixed backoff**, each retry waits the same amount of time. For example, waiting 2 seconds between every attempt:

```text
Retry 1: 2 seconds
Retry 2: 2 seconds
Retry 3: 2 seconds
Retry 4: 2 seconds
```

With **exponential backoff**, the wait interval grows exponentially. A simple formula is:

\[
  d_n = \min(d_0 \times m^{n-1}, d_{max})
\]

Where:

- \(d_n\) is the wait time before the \(n\)-th retry.
- \(d_0\) is the initial wait interval (`initialInterval`).
- \(m\) is the multiplier (`multiplier`), typically greater than 1.
- \(d_{max}\) is the maximum cap (`maxInterval`).

For example, `initialInterval = 1 second`, `multiplier = 2`, and `maxInterval = 10 seconds`:

| Retry attempt | Wait interval |
|---:|---:|
| 1 | 1 second |
| 2 | 2 seconds |
| 3 | 4 seconds |
| 4 | 8 seconds |
| 5 | 10 seconds |
| 6 | 10 seconds |

Once `maxInterval` is reached, subsequent retries do not increase further. This cap prevents the wait time from growing indefinitely.

## 3. Choosing initial interval, multiplier, and max interval

Three main parameters determine the shape of the retry schedule:

| Parameter | Meaning | Effect when increased |
|---|---|---|
| `initialInterval` | Initial wait time | Slows down retries right from the start. |
| `multiplier` | Growth factor between wait intervals | Wait intervals grow faster. |
| `maxInterval` | Maximum wait interval | Caps the pause duration of each retry. |

Choose parameters based on dependency characteristics and completion-time requirements:

- Dependencies that usually recover quickly can use a short initial interval.
- Services with longer recovery times may need a larger multiplier.
- `maxInterval` prevents retries from being delayed too long.
- The retry count must be finite so a record does not hold resources indefinitely.
- Total wait time must align with SLAs, partition hold time, and allowed processing time.

No single parameter set fits every topic. Payment processing, status updates, and data synchronization flows may have different requirements for latency, ordering, and retryability.

## 4. Configuring exponential backoff with DefaultErrorHandler

In Spring Kafka, `DefaultErrorHandler` handles listener exceptions and uses a `BackOff` to decide when to retry. `ExponentialBackOffWithMaxRetries` can be used to specify a maximum retry count along with an exponential schedule.

Configuration example:

```java
@Configuration
public class KafkaErrorConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);

        var backOff = new ExponentialBackOffWithMaxRetries(5);
        backOff.setInitialInterval(1_000L);
        backOff.setMultiplier(2.0);
        backOff.setMaxInterval(10_000L);

        var handler = new DefaultErrorHandler(recoverer, backOff);
        handler.addNotRetryableExceptions(InvalidOrderException.class);
        return handler;
    }
}
```

Key imports in the example belong to Spring Kafka:

```java
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.support.ExponentialBackOffWithMaxRetries;
```

`ExponentialBackOffWithMaxRetries(5)` sets a maximum of five retries after the initial processing attempt. With the parameters above, the wait schedule is 1, 2, 4, 8, and 10 seconds. The total number of times the listener can be invoked for a record is one initial attempt plus up to five retries, if all attempts fail and the record is not recovered earlier.

`DeadLetterPublishingRecoverer` illustrates the recovery step after retries are exhausted: the record is sent to a dead-letter topic (DLT) according to the default destination resolver or an application-configured resolver. The application must configure appropriate serializers, target topics, and DLT write permissions. If you do not want to publish to a DLT, another recoverer may be used, but you must clearly define how the record will be handled after retries are exhausted.

### 4.1 Configuring ErrorHandler on the listener container

If the application creates its own listener container factory, attach the error handler to the factory:

```java
factory.setCommonErrorHandler(kafkaErrorHandler);
```

In Spring Boot, a `CommonErrorHandler` bean may be auto-configured for Boot-created listener containers, depending on the version and how the application customizes the factory. If you have a custom-defined factory, verify that the factory is using the intended error handler.

Do not declare a `DefaultErrorHandler` and assume every listener uses it automatically. Identify the actual listener container and configure the error handler in the right place.

## 5. Backoff and attempt counts

When reading retry configuration, distinguish the **initial delivery** from the **number of retries**. In `ExponentialBackOffWithMaxRetries`, the constructor argument is the maximum number of retries. For example:

```java
var backOff = new ExponentialBackOffWithMaxRetries(3);
```

If the record fails continuously, the listener can be invoked up to four times: one initial attempt and three retries. After the final retry still fails, the error handler invokes the recoverer.

For other `BackOff` implementations, parameter semantics may differ. For instance, `FixedBackOff(interval, maxAttempts)` in Spring Framework uses retry counts per the `BackOffExecution` contract; read the exact API being used and verify the actual invocation count in integration tests.

A `BackOff` returns a wait interval for each retry. Once attempts are exhausted, `nextBackOff()` returns `BackOffExecution.STOP`; the error handler transitions to recovery. This creates a clear boundary between retrying and handling exhausted records.

## 6. Retry only recoverable errors

Not every exception should be retried. Classify errors before designing backoff:

| Error type | Examples | Typically appropriate policy |
|---|---|---|
| Transient | HTTP 503, brief timeout, database failover | Bounded retry with backoff. |
| Recoverable connection error | Broker or dependent service temporarily loses connection | Retry and monitor dependency health. |
| Invalid data | Missing `orderId`, schema-invalid payload | Do not retry repeatedly; move to DLT/quarantine. |
| Business violation | Order is in a state that disallows updates | Handle per business policy, usually no automatic retry. |
| Programming bug | Null pointer, incorrect mapping | Requires code fix; repeated retries usually do not help. |

`DefaultErrorHandler` has exceptions classified as non-retryable by default, and allows adding error types via `addNotRetryableExceptions()`. `addRetryableExceptions()` can be used to adjust classification according to business needs. Check the classification configuration of the Spring Kafka version in use, as default lists and handling may change across versions.

If a listener catches an exception and does not rethrow it, the error handler does not see that error and may treat the listener as having succeeded. When retries are desired, let the appropriate exception propagate out of the listener or report the error through a clearly designed mechanism.

## 7. Dead Letter Topic after retries are exhausted

Once backoff exhausts its retry count, the record needs a final outcome. A DLT is commonly used to hold the failed record along with metadata to support investigation:

- Source topic, partition, and offset.
- Record key, timestamp, and headers.
- Exception or failure cause details.
- Retry count or delivery attempt information if configured.
- Correlation ID or event ID for business tracing.

A DLT does not fix bad data by itself. It is a place to isolate the record for investigation, root-cause remediation, and controlled replay. Before replaying, confirm the bug is fixed, schemas are compatible, and business logic is idempotent.

If DLT publishing fails, do not silently treat the original record as successfully processed. Configure the recoverer and error handler so that recovery failures remain observable and are handled according to policy. A record that cannot be written to the DLT may need recovery retries or retention to avoid data loss.

## 8. Blocking retry and impact on partitions

With blocking retry via `DefaultErrorHandler`, the failed record is retried within the current consumption flow. During backoff and retries, the partition may be unable to continue processing subsequent records in normal order.

This preserves relatively clear ordering semantics: the failed record is reprocessed before the consumer moves forward. However, a prolonged failing record can increase lag for that partition. If backoff is long, the consumer thread may spend significant time waiting instead of processing new records.

Consider:

- Total retry duration for a single record.
- Number of partitions held by the consumer member.
- `max.poll.interval.ms` and processing time between polls.
- Possibility of pausing the container during long backoffs.
- Impact of one record blocking subsequent records in the same partition.

Spring Kafka provides `ContainerPausingBackOffHandler` for cases where the container should be paused during long backoffs. Actual pause duration is affected by `pollTimeout`; configure and test according to the version in use. Do not merely increase `max.poll.interval.ms` while ignoring the impact on group membership and recovery time.

## 9. Non-blocking retry with retry topics

If you do not want a failing record to block a partition during long waits, retry topics can be used. The record is moved to a retry topic with an appropriate processing delay; consumers of the main topic continue processing other records. When the retry topic reaches its scheduled processing time, the record is delivered back into the listener flow; if it continues to fail, it can pass through subsequent retry topics and eventually into the DLT.

Example with `@RetryableTopic`:

```java
@RetryableTopic(
        attempts = "6",
        backoff = @Backoff(
                delay = 1_000,
                multiplier = 2.0,
                maxDelay = 10_000),
        dltTopicSuffix = ".dlt")
@KafkaListener(topics = "orders")
public void onOrder(Order order) {
    orderService.process(order);
}
```

In this example, `attempts = "6"` is the total number of attempts, including the initial delivery. `@Backoff` describes the increasing delay schedule and maximum delay cap. Spring Kafka creates the retry topics and routes records according to the annotation's retry topic configuration.

Non-blocking retry has the advantage that a failed record does not hold the main consumer waiting for the entire backoff window. However, processing order can change: a later record in the same partition may be processed before the failed record is retried. Use this only when the business accepts such reordering or has versioning/idempotency to protect state.

Non-blocking retry topics have specific limitations depending on the Spring Kafka version, including restrictions with batch listeners and container transactions. Do not combine them with container transactions if your version does not support it; check the documentation and test semantics before deploying.

## 10. Jitter to avoid synchronized retries

Exponential backoff increases wait times, but multiple consumers can still fail at the same moment and retry on the exact same schedule. Requests can then bunch into waves, creating a thundering herd effect.

**Jitter** adds a random component to the wait time to spread out retry timestamps. For example, instead of every consumer retrying after exactly 8 seconds, each consumer can retry within a window around that mark according to the chosen policy.

Jitter is useful when:

- Multiple partitions or service instances call the same dependency.
- An incident starts at a single point in time, causing many requests to fail simultaneously.
- A dependency has throughput limits and spikes in requests must be avoided.

Do not assume every `BackOff` in Spring Kafka adds jitter automatically. Check the specific implementation; if needed, use an implementation that supports randomization or an appropriate custom `BackOff`. Even when adding jitter, preserve maximum wait limits and retry counts to uphold SLAs.

## 11. Calculating total retry time

Processing time for a record consists of listener execution time on each attempt plus the backoff intervals between attempts. With a schedule of 1, 2, 4, 8, and 10 seconds, total wait time between attempts is 25 seconds, not counting business logic execution and recovery time.

If each processing attempt averages 500 ms and there is one initial attempt plus five retries, business execution time is roughly 3 seconds. Theoretical total processing time is then about 28 seconds, excluding consumer, commit, recovery, and scheduling overhead.

Calculate total time using the formula:

\[
  T_{total} = \sum_{i=1}^{N} T_{process,i} + \sum_{j=1}^{N-1} d_j + T_{recovery}
\]

Where \(N\) is the total number of listener invocations, \(T_{process,i}\) is the processing time of the \(i\)-th attempt, \(d_j\) is the backoff interval between two attempts, and \(T_{recovery}\) is the time to send the record to the DLT or perform recovery.

This total time must match business requirements. If an event must finish within 10 seconds, a backoff configuration with 25 seconds of total delay fails the requirement even if each individual retry interval looks reasonable.

## 12. Observing retries and backoff in production

Monitor retries as part of system health, not just by counting exceptions:

- Number of retried records by topic, partition, and exception type.
- Average and distribution of attempt counts before success.
- Number of records that exhausted retries and moved to the DLT.
- Time from initial delivery to success or recovery.
- Consumer lag by partition during periods of elevated retries.
- Error rate and latency of dependencies called from the listener.
- Failures when publishing to the DLT or retry topics.

Logs should include source topic, partition, offset, event ID, exception class, and delivery attempt if available. Avoid turning very high-cardinality keys into metric labels; use logs/traces or aggregated metrics to avoid overloading the monitoring system.

A sudden spike in retries can signal a failing dependency, a schema change, or a release introducing a mapping bug. Correlate retry timestamps with deployments, configuration changes, and dependency metrics to find the root cause.

## 13. Testing exponential backoff

Testing must verify both attempt counts, wait intervals, and behavior after retries are exhausted. You can test `BackOff` in isolation by calling `start()` and `nextBackOff()` to verify the timing schedule, then use integration tests with a Kafka broker to verify the error handler and recovery.

Scenarios to include:

1. Listener fails on the first two attempts and then succeeds; verify invocation counts and retry intervals match configuration.
2. Listener fails continuously; verify retries stop at the exact configured limit.
3. An exception is classified as non-retryable; verify none of the configured backoff intervals are waited.
4. After retries are exhausted, verify the record is sent to the right DLT and source metadata is preserved.
5. Make DLT publishing fail; verify recovery failure is observed and the record is not silently lost.
6. With retry topics, verify the record traverses the topics per delay and eventually reaches the DLT.
7. Send many failing records simultaneously; observe dependency load and jitter effectiveness if the implementation supports it.
8. Verify record ordering when using blocking retry vs. non-blocking retry.

Do not use long `Thread.sleep()` calls in unit tests just to wait out backoff. Test the `BackOff` schedule directly or use an appropriate clock/test harness. For integration tests, use finite timeouts and clear conditions such as listener invocation counts or records appearing in the DLT.

## 14. Common configuration mistakes

- **Unlimited retries:** a record can hold the partition and resources indefinitely.
- **Multiplier too large:** wait times quickly hit max interval and make records wait too long.
- **No max interval set:** wait times can grow beyond business budgets if the implementation permits it.
- **Retrying permanent data errors:** creates load without being able to fix the cause.
- **Not calculating total retry time:** a record can breach SLAs even when each individual wait looks reasonable.
- **Confusing retry topic `attempts` with retry count:** with `@RetryableTopic`, `attempts` includes the initial attempt.
- **Assuming blocking retry does not affect later records:** retries can stall partition processing.
- **Using retry topics while still assuming original ordering:** later records can be processed before a record waiting to retry.
- **Not monitoring DLT publish failures:** records exhausting retries may not be recovered as expected.
- **Assuming exponential backoff always includes jitter:** instances can still retry in lockstep if sharing the same fixed schedule.

## 15. How to choose a strategy for each flow

| Need | Strategy to consider |
|---|---|
| Transient errors, few retries, partition order must be preserved | `DefaultErrorHandler` with blocking exponential backoff. |
| Dependency recovers in seconds and needs quick initial retries | Short initial interval, moderate multiplier, and appropriate max interval. |
| Many consumers retrying against the same dependency | Add jitter via a suitable implementation and limit total retry load. |
| Retries may drag on and partition must not be held waiting | Retry topics with `@RetryableTopic`, if ordering and model limits are acceptable. |
| Invalid data or unrecoverable errors | Classify as non-retryable and route to DLT/quarantine. |
| Need atomic Kafka outputs and offsets | Use container transactions and compatible error handling; evaluate retry topics separately. |

Exponential backoff must be designed alongside retry counts, exception types, recovery mechanisms, processing times, and ordering requirements. Choose wait intervals that give dependencies a chance to recover, set limits so records do not wait forever, and monitor retries as an operational signal. Once retries hit their limit, records must have a clear path for investigation or safe reprocessing.
