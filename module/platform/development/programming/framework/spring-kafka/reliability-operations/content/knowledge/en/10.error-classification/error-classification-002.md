# Retryable exceptions

In Spring Kafka, an exception thrown while a listener processes a record does not necessarily share the same remediation. A timeout caused by a temporarily unavailable dependent service may disappear after a few seconds; a malformed payload or a business rule violation usually keeps failing no matter how many times it is resent. Therefore, the system needs to classify exceptions to decide which records are retried, how many times they are retried, how long to wait, and when to move them to a recovery flow such as a dead-letter topic (DLT).

An exception is considered **retryable** when re-attempting processing has a chance of succeeding after waiting or after a temporary condition recovers. A **non-retryable** exception indicates an error that cannot resolve itself by running the same record again under the same conditions. This classification is an operational and business decision, not merely a property of a Java class.

Spring Kafka provides mechanisms such as `DefaultErrorHandler`, exception classification, backoff, `DeadLetterPublishingRecoverer`, and retry topics via `@RetryableTopic`. These mechanisms enable implementing an explicit retry policy, but they do not automatically make business operations idempotent or guarantee that a record will eventually be processed successfully.

## 1. What is a retryable exception?

A retryable exception is a type of error for which the application allows re-attempting record processing. Retrying makes sense when the cause is likely to change over time, such as:

- A database temporarily refuses connections.
- An HTTP service returns a timeout or temporary server error.
- A broker or network has just undergone a leader change.
- A resource is locked and can be released.
- A dependency is throttled and can recover after a wait period.

Non-retryable exceptions usually indicate an invalid record or request:

- The payload is missing a required field or has an invalid format.
- A value is outside the allowed business domain.
- The event type is not supported by the consumer.
- The schema is incompatible and requires the producer to emit properly formatted data.
- An operation is permanently rejected by business policy.

Some errors must be classified by context. HTTP 404 may be a permanent error if the resource does not exist, but it can be a temporary error if a service reading newly created data has not synchronized yet. HTTP 409 may be a conflict worth retrying after refreshing state, or a final business outcome. Classify based on the dependency's contract and business semantics.

| Exception group | Examples | Typical policy |
|---|---|---|
| Temporary infrastructure errors | Timeout, connection reset, broker unavailable | Retry with backoff and limits |
| Throttling errors | HTTP 429, temporary quota | Retry according to the wait time recommended by the dependency |
| Data contention errors | Deadlock, optimistic locking conflict | Bounded retry if the transaction can safely re-run |
| Data errors | Validation failure, malformed payload | Do not retry the same payload; route to DLT or data remediation flow |
| Configuration/permission errors | Wrong ACL, expired credential, non-existent topic | Alert and fix configuration; tight retries are usually unhelpful |
| Terminal business errors | Order already canceled, operation not allowed | Handle as a business outcome; do not retry like an infrastructure error |

## 2. How do exceptions flow through the listener container?

For synchronous record listeners, an exception thrown from the listener method is forwarded to the listener container's error handler. The error handler decides whether to retry, skip, recover, or send the record to a DLT.

~~~text
Kafka consumer poll
        |
        v
Listener receives record
        |
        v
Execute business logic
        |
   +----+----+
   |         |
Success   Exception
   |         |
   v         v
Ack/commit  CommonErrorHandler
             |
       +-----+------+
       |            |
    Retry      Retries exhausted
       |            |
       v            v
 Listener again Recoverer / DLT
                    |
                    v
              Confirm recovery
~~~

If the listener completes normally, the container handles acknowledgement according to the configured ack mode. If the listener throws an exception, the error handler classifies the exception and applies backoff. Once retries are exhausted, the recoverer can write the record to a DLT or perform another recovery action.

Exceptions occurring outside the listener thread managed by the container may not be seen by the error handler. For example, if a listener submits a task to an executor and returns, an exception occurring later on the worker thread does not automatically propagate back to the listener container. With asynchronous processing, the application must route exceptions to a dedicated failure handler and only acknowledge once the work completes or recovery has durably persisted the record.

## 3. Exception classification in DefaultErrorHandler

`DefaultErrorHandler` is a common error handler for record listeners. It combines exception classification, `BackOff`, and a recoverer to handle failed records.

Under the default policy of Spring Kafka versions featuring `DefaultErrorHandler`, most exceptions are retried; certain exceptions are considered fatal and are not retried because they typically cannot be resolved by resending the same record. Types commonly classified as fatal include:

- `DeserializationException`
- `MessageConversionException`
- `ConversionException`
- `MethodArgumentResolutionException`
- `NoSuchMethodException`
- `ClassCastException`

The default list and classification behavior may vary by version. Check the Spring Kafka documentation corresponding to the running dependency. Classification can be customized using methods such as `addNotRetryableExceptions(...)` and `addRetryableExceptions(...)`.

### 3.1. Marking exceptions as non-retryable

For example, an application does not want to retry invalid payloads or rejected business commands:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(recoverer, backOff);

    handler.addNotRetryableExceptions(
            InvalidOrderException.class,
            UnsupportedEventTypeException.class);

    return handler;
}
~~~

In this example, `FixedBackOff(1_000L, 2L)` sets a one-second wait interval and allows two retries after the initial processing attempt. The total number of times the listener can be invoked in this case is three if the record keeps failing. The recoverer sends records whose retries are exhausted or that are classified as non-retryable to the DLT according to the target configuration.

### 3.2. Marking exceptions as retryable

Exceptions can be added to the retryable group:

~~~java
handler.addRetryableExceptions(
        TemporaryInventoryException.class,
        RemoteServiceUnavailableException.class);
~~~

Adding explicit retryables is useful when the application has customized classification, changed default values, or wants to make the dependency's error contract explicit in configuration. If an exception is already retried under the default policy, adding it again may not change behavior.

Do not mechanically add all exceptions to the retryable group. `NullPointerException`, `IllegalArgumentException`, or programming bugs usually do not disappear after a few re-runs; retrying them can slow down processing and mask code defects.

### 3.3. Policy-driven classification configuration

When there are multiple exception groups, manage classification centrally rather than scattering `instanceof` logic across listeners. You can use Spring Kafka's classification APIs to declare which classes are retryable and which are not.

Note that classification typically checks exception types and may traverse the cause chain depending on configuration/version. If a business exception is wrapped inside `ListenerExecutionFailedException` or another wrapper exception, verify that the error handler recognizes the root exception. Avoid relying on exception message strings because messages can change or contain dynamic data.

## 4. Designing expressive exception classes

Exception types should express both the cause and the handling policy. Example:

~~~java
public class TemporaryInventoryException extends RuntimeException {
    public TemporaryInventoryException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}
~~~

A service calling a dependency can translate technical errors into meaningful exceptions:

~~~java
public Inventory reserve(String sku, int quantity) {
    try {
        return inventoryClient.reserve(sku, quantity);
    }
    catch (SocketTimeoutException ex) {
        throw new TemporaryInventoryException(
                "Inventory service timed out", ex);
    }
}
~~~

Do not catch every exception and wrap it in a single generic retryable exception. That can collapse validation errors, code bugs, permission errors, and infrastructure failures into the same retry policy. Preserve the original cause for logging and diagnostics while classifying based on the actual cause.

### 4.1. Cause chain and exception wrappers

An exception can be wrapped across multiple layers:

~~~text
ListenerExecutionFailedException
          |
          v
ServiceException
          |
          v
TemporaryInventoryException
          |
          v
SocketTimeoutException
~~~

If classification only inspects the outermost exception, the policy may fail to match the root exception. Spring Kafka supports traversing the cause chain in its classification APIs; exact capabilities and defaults depend on the version. Verify actual behavior with an integration test using exception wrappers.

Do not classify solely on a generic class name like `RuntimeException` if that class represents multiple causes with different policies in the system. Dedicated domain exceptions keep configuration readable and reduce confusion.

## 5. Backoff and retry counts

Immediate retries can put heavy pressure on a failing dependency. Backoff introduces a wait interval between attempts so the dependency has time to recover and to avoid retry storms.

Several backoff styles:

| Type | How it works | Suitable cases |
|---|---|---|
| Fixed | Every retry waits the same interval | Simple temporary errors needing predictable policy |
| Exponential | Wait interval grows after each retry | Dependencies needing longer recovery time |
| Exponential with max interval | Grows progressively but capped at a maximum | Balancing recovery speed with time limits |
| Randomized/jitter | Adds randomness to the wait interval | Preventing multiple consumers from retrying at the same instant |

Fixed backoff example:

~~~java
new FixedBackOff(2_000L, 3L);
~~~

These values allow three retries, each two seconds apart, after the initial processing attempt. If the record always fails, the listener can be invoked four times in total before recovery.

Exponential backoff example:

~~~java
ExponentialBackOffWithMaxRetries backOff =
        new ExponentialBackOffWithMaxRetries(4);
backOff.setInitialInterval(1_000L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(10_000L);
~~~

The wait interval starts at one second, doubles after each attempt, and is capped at ten seconds. `ExponentialBackOffWithMaxRetries(4)` specifies the number of retries per Spring Kafka's API, i.e., four retries after the initial attempt. Check the library version when calculating total attempts and maximum duration.

### 5.1. Calculating total retry duration

The retry policy must fit within the business time budget. If a record is allowed to complete within at most 60 seconds, but backoff and processing time can stretch to several minutes, the record will violate the SLA even if it eventually succeeds.

Total duration must account for:

- Initial processing time.
- Number of retries.
- Backoff intervals between attempts.
- Duration of each dependency call.
- Time to publish to the DLT or perform recovery.
- Time the consumer is paused or waiting for the record in a retry topic.

Do not add up backoff intervals alone; a 30-second request timeout repeated three times can dominate total duration even with short backoffs.

## 6. Blocking retry with DefaultErrorHandler

Blocking retry re-executes the record on the listener container's processing thread. Failed records can be seeked/redelivered according to the error handler's policy; subsequent records in the same partition may have to wait depending on how the container handles them.

Advantages:

- Easy to understand and configure within the same listener container.
- Can preserve partition processing order better than moving records to retry topics.
- Suitable for temporary errors with short recovery times.
- Does not require creating extra retry topics for each backoff tier.

Trade-offs:

- The consumer thread is occupied during retry/backoff.
- A failing record can slow down subsequent records in the partition.
- Long retries can increase consumer lag or interact with `max.poll.interval.ms`.
- A widespread dependency outage can cause many consumers to retry simultaneously and generate extra load.

Blocking retry is usually suitable when the dependency recovers quickly and partition ordering matters. Bound retries and backoff, and monitor processing duration and lag.

## 7. Non-blocking retry with retry topics

Spring Kafka supports non-blocking retry via `@RetryableTopic`. When the listener fails, the record is moved to the retry topic matching the backoff tier. The main topic consumer can continue processing subsequent records while the failed record waits for its retry turn.

Example:

~~~java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
                delay = 1_000,
                multiplier = 2.0,
                maxDelay = 10_000),
        include = {
                TemporaryInventoryException.class,
                RemoteServiceUnavailableException.class
        },
        exclude = {
                InvalidOrderException.class
        },
        dltTopicSuffix = ".DLT")
@KafkaListener(topics = "orders", groupId = "billing")
public void consume(OrderCreated event) {
    billingService.process(event);
}
~~~

In the annotation, `attempts` is the total number of attempts per retry topic convention, including the initial processing attempt. For example, `attempts = "4"` typically means one main attempt and at most three retries. Check the actual Spring Kafka version and exception classification behavior, especially when using `include`, `exclude`, or centralized retry topic configuration.

Non-blocking retry suits errors that need longer waits or when you do not want a failing record to block all progress on the main partition. However, a retried record may arrive after newer records. Therefore, business ordering among events with the same key can change.

Do not use retry topics if the business strictly requires every record in a partition to complete in its original order without an ordering-protection mechanism. You may need blocking retry or a workflow designed around aggregate/versioning.

## 8. Exception classification in retry topics

Retry topics have their own exception classification mechanism. You can declare retryable classes with `include`, non-retryable classes with `exclude`, or configure class names via corresponding properties depending on the API version.

Principles:

- Only put temporary exceptions in the retry list when retrying has a chance of succeeding.
- Put data and terminal business exceptions in the non-retryable group.
- Check how the cause chain is evaluated when the listener throws wrapper exceptions.
- Do not let `include` and `exclude` conflict without understanding precedence.
- Verify the attempt count, retry topic names, backoff, and DLT created as expected.

Retry topics can auto-create topics if configuration permits, but production environments usually need to manage topics, partitions, replication, ACLs, and retention through infrastructure workflows. Do not rely solely on auto-create while bypassing cluster policies.

## 9. Deserialization and exceptions before the listener runs

Not every exception originates inside the listener body. If the consumer fails to deserialize a key or value, the listener may never receive an object to process. This is why deserialization errors are usually classified as fatal/non-retryable by default: resending the same bytes with the same deserializer generally cannot fix the payload.

Spring Kafka provides `ErrorHandlingDeserializer` to wrap the actual deserializer and pass error information to the error handling mechanism. The delegate must be configured to match the producer format, and you must verify how raw payloads are retained for recovery.

When encountering a deserialization error:

1. Identify the payload and the serializer/schema version emitted.
2. Check the consumer deserializer, trusted packages, and type headers if using JSON.
3. Check recent schema changes.
4. Retain the raw payload if data policy allows.
5. Route the failed record to the DLT or investigation workflow.
6. Fix the producer/schema/consumer and then perform a controlled replay.

Retrying the same invalid payload repeatedly usually only increases lag and log noise. Only retry deserialization if the root cause is truly temporary, such as a schema lookup component being temporarily unavailable and the exception being classified accordingly.

## 10. Retryable exceptions and idempotency

At-least-once delivery can redeliver a record after the listener has performed partial business side effects without yet committing the offset. Exception-driven retries can also run the same record multiple times. Therefore, all side effects need duplicate protection.

With a database, you can store the event id in an inbox table within the same transaction as the business change:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Processing flow:

1. Start the database transaction.
2. Insert the event id into `processed_events`.
3. If the event id already exists, do not repeat business side effects.
4. If the event id is new, execute the business update.
5. Commit the database transaction.
6. Let the listener complete and the container commit the offset.

For HTTP APIs, use an idempotency key if the target API supports it. If a timeout leaves the request outcome unknown, reconcile before resending a non-repeatable operation.

Do not generate a new event id for each retry. Retries and the DLT must preserve the original identifier so deduplication recognizes that it is still the same event.

## 11. Multi-layer retries and retry storms

A record can be retried at multiple layers:

- `DefaultErrorHandler` in Spring Kafka.
- Retry topics via `@RetryableTopic`.
- Spring Retry or service-level retries.
- HTTP client retries.
- JDBC/database retries.
- Retries inside the dependency itself.

If each layer has three retries, the total number of dependency calls can multiply rapidly. For instance, three layers with three attempts each can generate up to 27 calls under certain nested retry configurations.

Designate a primary responsible layer for each error type. If the dependency client already retries timeouts, the listener error handler should not repeat a long retry chain without accounting for total duration. Set attempt limits and overall deadlines, and propagate correlation id and event id across attempts.

A retry storm occurs when many consumers continuously retry against a failing dependency. Backoff with jitter, concurrency limits, circuit breakers, and rate limits can reduce pressure. When the dependency recovers, avoid letting the entire retry backlog hit it all at once.

## 12. Choosing a retry policy by error type

A policy table helps development and operations teams apply a consistent classification:

| Exception/condition | Retry? | Backoff | Action after retries exhausted |
|---|---|---|---|
| Temporary socket timeout | Yes | Exponential, bounded | DLT and alert if still failing |
| HTTP 503 | Yes | Exponential with jitter | DLT or longer retry topic per SLA |
| HTTP 429 | Yes, per API contract | Respect Retry-After if present | DLT/alert when deadline exceeded |
| Database deadlock | Bounded | Short, with jitter | DLT or manual handling |
| Invalid payload | No | No retry | DLT and fix data |
| Unsupported event type | No | No retry | DLT; check producer/consumer compatibility |
| Authorization failure | Usually no tight retries | Can retry after credentials/config are fixed | Operations alert |
| Business rule rejection | Depends on business outcome | Usually no retry | Record rejection outcome |

These are starting guidelines. An error should only be retried when the dependency can recover within the allowed timeframe and re-invoking does not produce duplicate side effects.

## 13. DLT and recovery after retries are exhausted

When an exception is non-retryable or a record has exhausted its retry count, the recoverer can send the record to a DLT. The DLT allows the consumer group to keep processing other records while preserving the data needed for investigation.

Information that should be retained:

- Source topic, partition, and offset.
- Original key and event id.
- Exception class and error message.
- Failure timestamp and attempt count if available.
- Correlation id or trace id to locate related logs.
- Schema version or metadata needed for replay.

Do not log full sensitive payloads. Restrict read access to the DLT and set retention long enough for the investigation workflow.

### 13.1. Do not acknowledge source offset before durable recovery

If publishing to the DLT fails, the record must not be treated as successfully recovered. Configure the recoverer and error handler so DLT send errors are observed and the source offset is not committed in a way that loses the record. In Spring Kafka versions that support it, configure the recoverer to wait for the publish result and fail if sending fails.

### 13.2. DLT replay

Replay must preserve the original event id and be executed only after the root cause has been fixed. Before replaying:

1. Categorize records and identify the cause.
2. Fix code, schema, data, or dependency.
3. Test with a representative sample of records.
4. Replay in rate-limited batches.
5. Monitor succeeded count and records that continue failing.
6. Reconcile business impact to detect duplicate or missing events.

Do not automatically replay the entire DLT immediately after a deployment without checking the root cause and side effects.

## 14. Observing retries and exception classification

Metrics and logs must show why a record is retrying, how many times it has been attempted, and how much time remains before the deadline.

Metrics to track:

- Listener exception rate by error category.
- Retry count/rate and backoff duration.
- Number of records routed to retry topics.
- DLT incoming rate and oldest record age.
- Consumer lag and processing duration.
- Dependency timeout/error rate.
- DLT publish failure count.

Logs should include event id, topic, partition, offset, consumer group, exception class, and attempt number if available. Do not use event id or offset as high-cardinality metric tags; store them in structured logs for per-record lookup.

Alerts should be based on trends and SLAs:

- Sustained increase in retry rate.
- A spike in a specific exception class after deployment.
- New records or rapid growth in the DLT.
- Oldest record age exceeding business deadlines.
- Dependency error rate rising alongside retries.
- Consumer lag rising despite steady incoming rate.

## 15. Runbook for common scenarios

### 15.1. Sudden spike in retries

1. Group exceptions by class and dependency.
2. Identify start time and recent release/config changes.
3. Check dependency latency, timeouts, throttling, and health.
4. Determine whether retries are adding extra load to the dependency.
5. Limit retries or concurrency per policy if needed.
6. Monitor lag and recovery time once the dependency stabilizes.

### 15.2. Exception not retrying despite being considered temporary

1. Inspect the outermost exception and cause chain.
2. Confirm the exception class was added to the correct error handler classification.
3. Check whether the listener uses the expected container factory.
4. Verify no other classification marks the exception non-retryable.
5. Check the Spring Kafka version and cause traversal behavior.
6. Create an integration test using the actual exception wrapper.

### 15.3. Data exception being retried continuously

1. Identify the exception class and sample record.
2. Check default classification and custom configuration.
3. Mark the data exception as non-retryable if resending the same payload cannot fix the error.
4. Route the record to the DLT.
5. Fix the producer or source data, then perform a controlled replay.

### 15.4. DLT growth after a deployment

1. Group DLT records by exception class, schema version, and listener.
2. Correlate error timestamps with release/config changes.
3. Check serialization, validation, and dependencies.
4. Roll back or release a fix if the cause is in code.
5. Test representative records before replaying.
6. Reconcile business outcomes after replay.

### 15.5. Consumer lag rising even though retries appear to succeed

1. Check whether blocking backoff is holding partitions too long.
2. Check the number of retry layers and total dependency call duration.
3. If using retry topics, inspect lag on both the main topic and retry topics.
4. Check hot partitions and downstream capacity.
5. Adjust backoff/attempts according to SLA and monitor oldest record age.

## 16. Testing exception classification

Do not test only the happy path. Integration tests must prove that exceptions are classified properly and offsets advance only after safe processing or recovery.

Required scenarios:

1. A retryable exception fails twice and then succeeds.
2. A retryable exception exhausts retries and is routed to the DLT.
3. A non-retryable exception goes straight to recovery without retrying.
4. An exception wrapped in a cause chain is still classified correctly.
5. DLT publish fails and the source offset is not acknowledged, preventing record loss.
6. Consumer restarts after database commit but before offset commit; idempotency prevents duplicate side effects.
7. Dependency returns 429/503 and backoff behaves appropriately.
8. Retry topics alter ordering; business logic still handles it properly or design selects blocking retry.
9. Asynchronous worker fails outside the listener thread and the failure handler receives the exception.

Tests should verify listener invocation counts, destination topics receiving records, committed offsets, and business outcomes. Do not merely assert that an exception was logged.

## 17. Common design mistakes

**Retrying every exception:** Code bugs, malformed payloads, and terminal business errors do not fix themselves on retry. Classify by cause.

**Infinite retries:** A failing record can block a partition or create an unbounded backlog. Set attempt limits and overall deadlines.

**Backoff too short:** Consumers can trigger a retry storm against a failing dependency. Use appropriate backoff and jitter when needed.

**Wrapping every error in one retryable exception:** Loses cause information and causes permanent errors to be retried.

**Not preserving the root cause:** When only a generic wrapper remains, classification and investigation become difficult.

**Multi-layer retries without calculating total:** Dependency call counts can grow exponentially.

**Acking before durable side effects:** Business effects can be lost if the record is not redelivered.

**Treating the DLT as indefinite storage:** A DLT needs ACLs, retention, alerts, ownership, and a replay workflow.

**Assuming retry topics preserve order:** Non-blocking retries allow newer records to bypass records waiting for retry.

## 18. Implementation checklist

### Exception classification

- [ ] Distinguished temporary, data, configuration, and business errors.
- [ ] Exception classes express their cause clearly.
- [ ] Cause chain handling matches the Spring Kafka version in use.
- [ ] Default fatal/non-retryable classifications have been reviewed.
- [ ] Retryable and non-retryable exceptions are configured centrally.

### Retry policy

- [ ] Finite retry count is configured.
- [ ] Backoff matches dependency characteristics and SLA.
- [ ] Total processing duration and per-attempt timeouts are accounted for.
- [ ] No unintended overlapping retry layers exist.
- [ ] Blocking retry or retry topics chosen based on ordering requirements.

### Recovery and reliability

- [ ] Recoverer/DLT is configured with adequate partitions, ACLs, and retention.
- [ ] DLT publish failure does not erroneously acknowledge the source offset.
- [ ] Consumer is idempotent when records are redelivered.
- [ ] Replay is rate-limited and audited.
- [ ] Metrics, alerts, and runbooks exist for retry/DLT.

### Testing

- [ ] Retryable exceptions are retried the exact configured number of times.
- [ ] Non-retryable exceptions are not unnecessarily retried.
- [ ] Cause chains and exception wrappers are tested.
- [ ] DLT failures and consumer crashes are tested.
- [ ] Side effects are not duplicated when records are redelivered.

## Conclusion

Retryable exceptions define the error types that have a chance of recovering when retrying a record. Spring Kafka lets you configure classification in `DefaultErrorHandler`, set finite backoff, and route unprocessable records to a recoverer or DLT; retry topics support longer waits without holding records on the main stream. The right policy depends on error cause, business deadlines, partition ordering, and duplicate tolerance. Keep exception types expressive, bound total retries, guarantee idempotency, and test recovery paths so records are not lost when dependencies or the DLT experience incidents.
