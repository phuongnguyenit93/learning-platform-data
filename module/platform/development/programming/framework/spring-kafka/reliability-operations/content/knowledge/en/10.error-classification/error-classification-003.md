# Not-retryable exceptions

In Spring Kafka, not every exception should be retried. Retrying is useful when an error is likely to clear after a period of time, such as a temporarily overloaded database or an interrupted network connection. For errors originating from invalid data, unsupported event versions, or misconfiguration, resending the same record usually only adds load and slows down subsequent records.

A **not-retryable exception** is an exception classified so that the error handler does not re-invoke the listener under the standard retry policy. When encountering this exception, Spring Kafka proceeds directly to the recovery step. Recovery can send the record to a Dead Letter Topic (DLT), write it to a quarantine area, or execute an alternative application-defined action.

Not retrying does not mean automatically deleting the record. The error handler decides whether an exception is retried; the recoverer decides what to do with the record when it is not retried or when retries are exhausted. These two responsibilities must be configured together.

## 1. Distinguishing temporary errors from errors that cannot be fixed by retrying

Retry decisions must be based on root cause and recoverability, not just the exception name. The same general exception type can represent many different causes. For example, `RuntimeException` does not tell you whether an error is temporary; you must inspect the specific exception and underlying cause.

| Error group | Examples | Usually appropriate policy |
|---|---|---|
| Invalid data | Missing required field, malformed format, value out of valid range | Do not retry; route to DLT or business rejection workflow |
| Unsupported event version | Consumer does not recognize the schema/version published by producer | Do not retry until code or schema is updated |
| Conversion/deserialization errors | Payload cannot be converted to the data type expected by the listener | Usually do not retry the same payload; store original record and metadata for investigation |
| Deterministic programming bugs | Incorrect mapping, invalid cast, calling non-existent method | Do not retry blindly; fix code or roll back release |
| Temporary dependency errors | Database timeout, connection reset, short-term downstream overload | Bounded retry with backoff and load limits |
| Temporary resource errors | Lock contention, temporary connection pool exhaustion, time-bounded throttling | Controlled retry if dependency is expected to recover |
| Configuration/access errors | Wrong credentials, missing ACL, topic missing due to incomplete deployment | Usually do not retry tightly; alert and fix configuration or permissions |
| Business rejection decisions | Order rejected according to business rules | Handle as an intentional business outcome; do not use retries to alter the decision |

For example, a database write request that times out may succeed when retried after a few seconds. However, an event with `currency="XYZ_UNKNOWN"` will keep failing even after 100 retries if the code does not support that currency. Retrying the second case only increases consumer lag and log noise.

Do not classify all `4xx` errors or all `5xx` errors under one blanket rule when the listener calls an HTTP service. A `429 Too Many Requests` may recover after waiting; a `400 Bad Request` due to an invalid payload usually cannot be fixed by retrying. A `503 Service Unavailable` may be temporary, but requires backoff and a total time limit. Translate dependency errors into specific exceptions at the adapter layer so the error handler can classify accurately.

## 2. Exception classification in Spring Kafka

Spring Kafka uses an exception classifier in error handling to decide whether an exception is retryable. With `DefaultErrorHandler`, the application can add non-retryable exceptions via `addNotRetryableExceptions(...)`, or declare retryable exceptions via `addRetryableExceptions(...)`.

Starting in Spring Kafka 2.8, `DefaultErrorHandler` is the common error handler used in place of older error handlers such as `SeekToCurrentErrorHandler` for standard record listener flows. Older versions have different APIs and behavior; verify the exact Spring Kafka version in the project before applying configuration.

`DefaultErrorHandler` includes a default set of exceptions considered fatal (non-retryable) in modern versions, typically including:

- `DeserializationException`
- `MessageConversionException`
- `ConversionException`
- `MethodArgumentResolutionException`
- `NoSuchMethodException`
- `ClassCastException`

These exceptions usually indicate that the consumer cannot convert or bind the record into the listener method under the current configuration. Retrying the same record typically does not change the outcome. The application still needs an appropriate recoverer to retain the record and error information.

The default list may change across versions. Do not rely on memory or an online snippet to infer the full active classification; check the documentation for the version managed by your project's Spring Boot dependencies.

### 2.1. Adding non-retryable exceptions

For example, an order-processing system has two deterministic errors: invalid order data and unsupported event version. These errors are routed directly to the recoverer instead of being retried:

```java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);
    recoverer.setFailIfSendResultIsError(true);

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 3L));

    handler.addNotRetryableExceptions(
            InvalidOrderException.class,
            UnsupportedEventVersionException.class);

    return handler;
}
```

In this example, `FixedBackOff(1_000L, 3L)` allows up to three retries after the initial delivery for exceptions in the retryable group. `InvalidOrderException` and `UnsupportedEventVersionException` are recovered immediately when classified as not-retryable. The example's default recoverer sends records to a DLT topic per `DeadLetterPublishingRecoverer` convention; ensure the DLT has enough partitions, compatible serializers, and write permissions.

`setFailIfSendResultIsError(true)` instructs the recoverer to surface errors if sending to the DLT fails in Spring Kafka versions supporting this API. Without detecting publish failures, the application risks treating recovery as successful when the record has not been stored in the DLT. Verify timeouts, send results, and the behavior of the version in use.

### 2.2. Declaring retryable exceptions

Retryable exceptions can be added when the application needs an explicit classification for temporary errors:

```java
handler.addRetryableExceptions(
        InventoryServiceUnavailableException.class,
        TransientDatabaseException.class);
```

Exceptions marked as retryable will use the configured backoff. Only add exceptions when there is reason to believe retrying can succeed. Do not mark a generic exception like `Exception` or `RuntimeException` as retryable because doing so can turn programming and data errors into prolonged retries.

If the same class or parent/child classes appear in both retryable and not-retryable lists, the outcome depends on how the classifier stores and looks up classifications. Avoid overlapping declarations. Each exception should have a clear, testable policy.

## 3. Exceptions wrapped inside other exceptions

In a listener container, the root exception may be wrapped by an exception from Spring Kafka or another framework. For example, the listener throws `InvalidOrderException`, but an upper call layer wraps it inside `ListenerExecutionFailedException` or a generic application exception.

```text
ListenerExecutionFailedException
        |
        +-- cause: InvalidOrderException
```

When the classifier inspects only the outermost exception, the application may accidentally retry an error that is non-retryable. Spring Kafka supports classification along the cause chain; exact behavior and configuration details depend on the version. Preserve the original cause when wrapping exceptions, do not strip cause information, and verify that the classifier traverses the cause chain as intended.

Example of what not to do:

```java
try {
    orderService.validate(event);
}
catch (InvalidOrderException ex) {
    throw new RuntimeException("Cannot process event");
}
```

The code above loses the original cause. You should preserve the exception as the cause:

```java
try {
    orderService.validate(event);
}
catch (InvalidOrderException ex) {
    throw new OrderProcessingException("Cannot process event", ex);
}
```

Or let the domain exception propagate directly to the error handler if no extra context is needed. If the application uses wrappers, configure and test cause traversal on the exact Spring Kafka version. Do not assume all wrappers are classified by cause without verification.

## 4. Not-retryable does not mean discarding the record

When `DefaultErrorHandler` receives a non-retryable exception, it skips retries and calls the recoverer. The recoverer decides how the record is handled. If using `DeadLetterPublishingRecoverer`, the record is sent to the DLT; if using a custom recoverer, the application can save the record and metadata to another error store.

```text
Listener
   |
   v
Exception
   |
   v
Exception classifier
   |
   +---- retryable --------> BackOff --> invoke listener again
   |
   +---- not-retryable ----> Recoverer immediately
                                  |
                                  +--> DLT / quarantine / action
```

Without a proper recoverer configured, the error handler's default behavior may only log when a record is considered exhausted/recovered. Logs are not durable storage for replay. For critical business data, configure a queryable DLT or quarantine store and set alerts when records are routed there.

Do not use not-retryable as a way to silently drop failing records. Before skipping a record, you need clear business rules, an audit trail, and reconciliation capability if that data affects downstream state.

## 5. Using a DLT for non-retryable exceptions

A DLT isolates unprocessable records from the main flow so the consumer can keep moving forward. An illustrative configuration:

```java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    kafkaTemplate,
                    (record, exception) -> new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));

    recoverer.setFailIfSendResultIsError(true);

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));

    handler.addNotRetryableExceptions(
            InvalidOrderException.class,
            UnsupportedEventVersionException.class);

    return handler;
}
```

The resolver sends the record to a topic with the `.DLT` suffix and preserves the partition index. Therefore, the DLT topic must have enough partitions corresponding to the source topic. If the DLT has fewer partitions, use a resolver that maps to a valid partition or create the destination topic with a matching partition count.

Records in the DLT should retain source metadata such as original topic, partition, offset, timestamp, exception, and event ID. Specific headers added by Spring Kafka depend on the version. The DLT also requires replication, retention, ACLs, monitoring, and a replay workflow. A record sent to the DLT still needs human or automated investigation to determine remediation.

If the listener receives deserialized data, the DLT publisher needs a serializer compatible with those key/value types. If the error occurs before the value is deserialized, the payload may be `byte[]`; the template configuration must handle raw byte data as well. With multiple value types, consider a type-dispatching serializer or dedicated templates.

## 6. Deserialization exceptions and ErrorHandlingDeserializer

A deserialization error can happen before the listener method is invoked. If the consumer uses a raw deserializer directly and deserialization fails during `poll()`, the listener has no chance to catch the exception as a regular business error.

Spring Kafka provides `ErrorHandlingDeserializer` to catch errors from the delegate deserializer and place error details in the record headers, enabling container error handling to process the record. Configuration example:

```properties
spring.kafka.consumer.key-deserializer=org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
spring.kafka.consumer.value-deserializer=org.springframework.kafka.support.serializer.ErrorHandlingDeserializer

spring.kafka.consumer.properties[spring.deserializer.key.delegate.class]=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.properties[spring.deserializer.value.delegate.class]=org.springframework.kafka.support.serializer.JsonDeserializer
spring.kafka.consumer.properties[spring.json.value.default.type]=com.example.events.OrderCreated
spring.kafka.consumer.properties[spring.json.trusted.packages]=com.example.events
```

This is an example for string keys and JSON values. Type mapping properties, trusted packages, and delegate deserializers must match the producer's actual schema. When deserialization fails, `DefaultErrorHandler` can recognize `DeserializationException` from headers and handle it according to default or custom classification.

Do not infinitely retry a payload that the deserializer cannot read. When the producer releases a new schema, you may need to upgrade the consumer or enforce schema compatibility; in the meantime, the DLT preserves the original payload for replay after the application is updated.

## 7. Business errors: exception or rejection outcome?

Not every unacceptable business case should be represented as a technical exception. For example, an order exceeding a credit limit may be a valid workflow outcome: the system rejects the order and emits `OrderRejected`. Throwing `InvalidOrderException` and sending it to a DLT may obscure business semantics and create unnecessary investigation backlogs.

Distinguish between:

- **Business rejection:** an expected business outcome that needs to be recorded as a normal state. Handle directly, update state, and emit an outcome event if needed.
- **Invalid message:** a record that violates the data contract or cannot be mapped into a valid command. Do not retry the same payload; quarantine or DLT.
- **Transient infrastructure failure:** unable to complete the business action because a dependency is temporarily down. Bounded retry with backoff.
- **Unexpected programming failure:** a bug or violated invariant. Requires alerting, investigation, and usually avoiding blind retries.

If a business rule can change over time, retry decisions need careful thought. For instance, insufficient account balance today may be a final business rejection, or a waiting state if the system supports retrying after balance top-up. Model state explicitly rather than using infinite retries as a queue waiting for a business condition.

## 8. Not-retryable with non-blocking retry topics

Spring Kafka provides a non-blocking retry mechanism via `@RetryableTopic`. This moves records to retry topics instead of waiting to retry on the source partition. You can specify non-retryable exceptions using the `exclude` attribute:

```java
@RetryableTopic(
        attempts = "4",
        exclude = {
                InvalidOrderException.class,
                UnsupportedEventVersionException.class
        },
        dltTopicSuffix = ".DLT")
@KafkaListener(topics = "orders", groupId = "billing-service")
public void consume(OrderCreated event) {
    billingService.process(event);
}
```

In this configuration, exceptions listed in `exclude` bypass regular retry topics and are handled via the retry-topic mechanism's terminal/DLT branch. Check the DLT policy, attempt count, backoff, and API version in your application. With this annotation, attempt counts and retry topic names are managed by the non-blocking retry mechanism, unlike `DefaultErrorHandler`'s `FixedBackOff`.

Non-blocking retry lets the source partition keep processing other records while the failing record waits for retry. In return, relative ordering among records may change: a later record may be processed before a record sitting in a retry topic. If the business requires strict per-key ordering, evaluate carefully before using retry topics.

Do not configure multiple retry mechanisms simultaneously on the same listener without understanding their execution order. `DefaultErrorHandler` handles exceptions at the listener container level; `@RetryableTopic` sets up a dedicated retry topic flow. Choose a clear model and avoid layering multiple retry mechanisms that make total attempts and duration unpredictable.

## 9. Batch listeners and not-retryable exceptions

With batch listeners, a single poll can return multiple records in a list. When one record fails, the error handler needs to know which record failed so it can commit the already-processed portion and recover the failing record. Spring Kafka supports `BatchListenerFailedException` so the listener can specify the failing index or record.

Example:

```java
@KafkaListener(topics = "orders", groupId = "batch-billing")
public void consume(List<ConsumerRecord<String, OrderCreated>> records) {
    for (int i = 0; i < records.size(); i++) {
        ConsumerRecord<String, OrderCreated> record = records.get(i);
        try {
            billingService.process(record.value());
        }
        catch (InvalidOrderException ex) {
            throw new BatchListenerFailedException(
                    "Invalid order payload", ex, i);
        }
    }
}
```

`DefaultErrorHandler` can use the record position in the batch to determine the processed portion and the record to retry or recover. For exceptions classified as not-retryable, the failing record can be sent directly to the recoverer per handler policy. Records after the failing position may be redelivered depending on acknowledgment mode and batch recovery semantics.

If a batch listener throws a generic exception without identifying the failing record, the handler may have to reprocess the entire batch. This can create duplicates for records already processed before the exception occurred. Therefore, batch listeners must accurately pinpoint the failing record and keep side effects idempotent.

## 10. BackOff and retry policy still matter

Not-retryable exceptions go straight to recovery, while remaining exceptions still require a sensible retry policy. Do not use infinite retries for infrastructure errors; a prolonged dependency outage can make the consumer hold partitions too long, increase lag, and put pressure on brokers or downstream services.

Bounded retry example:

```java
ExponentialBackOffWithMaxRetries backOff =
        new ExponentialBackOffWithMaxRetries(4);
backOff.setInitialInterval(1_000L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(10_000L);

DefaultErrorHandler handler = new DefaultErrorHandler(recoverer, backOff);
handler.addNotRetryableExceptions(InvalidOrderException.class);
```

Increasing backoff avoids hammering a dependency during an outage. In production, choose the retry count and max wait time based on business latency, dependency timeouts, `max.poll.interval.ms`, and acceptable lag. If retry duration exceeds poll limits or the listener container cannot poll on time, evaluate pause/resume, container behavior, or non-blocking retry topics.

## 11. Testing classification and recovery

Tests should verify both the retry decision and the final action taken on the record:

1. Send a valid record and verify the listener processes it once.
2. Send a record causing `InvalidOrderException`; verify the listener is not re-invoked per backoff and the recoverer is called immediately.
3. Send a record causing `TransientDatabaseException`; verify the listener is retried the exact number of times with the right backoff.
4. Wrap a non-retryable exception in a wrapper; verify cause traversal produces the designed behavior.
5. Simulate a DLT publish error; verify recovery is not considered successful and the offset does not advance past that record.
6. Verify the DLT contains the required payload, key, headers, and source metadata.
7. For batch listeners, verify the index in `BatchListenerFailedException` points to the exact failing record.
8. With `@RetryableTopic`, verify exceptions in `exclude` go straight to the terminal/DLT path while other exceptions flow through retry topics as configured.

Do not only assert how many times the listener was called. Verify committed offsets, records in the DLT, logs, and recovery metrics to catch cases where a record was skipped without being persisted anywhere.

## 12. Observability and operations

Metrics to track include:

- Exception count by class and topic.
- Retry count by error type.
- Records routed straight to the recoverer due to not-retryable classification.
- DLT publish successes, failures, and timeouts.
- Consumer lag and age of the oldest unprocessed record.
- DLT record growth rate and backlog awaiting replay.
- Error rate by application version or schema version.

Do not use event ID, order ID, or offset as high-cardinality metric labels. Store record identifiers in controlled logs or traces. Recovery logs should include topic, partition, offset, event ID, exception class, cause, and DLT destination so on-call engineers can locate records.

When the not-retryable rate spikes suddenly after a release, inspect schema compatibility, mappings, validation rules, and domain model changes. When the DLT grows due to invalid input data, coordinate with the producer or upstream system to stop emitting bad data. When the DLT grows due to a programming bug, roll back or fix the consumer version before bulk replaying.

## 13. Common classification pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Data errors retried multiple times | Exception not added to not-retryable classification | Add specific exceptions via `addNotRetryableExceptions` and check cause chain |
| Temporary errors go straight to DLT | Generic exception or parent class classified as not-retryable | Narrow classification; distinguish exceptions by cause |
| Excluded exception still retries | Listener uses a different error handler/factory or a different retry mechanism | Verify the right factory and distinguish `DefaultErrorHandler` from `@RetryableTopic` |
| No record in DLT but offset advanced | Recoverer does not surface publish failure or recovery action is not durable | Enable send result checks, monitor recovery, and verify offsets |
| Wrapper causes mis-classification | Root cause lost or cause traversal differs from expectation | Preserve cause when wrapping and configure/test classifier per version |
| Valid records routed to DLT | Validation or exception mapping too broad | Narrow exception conditions; verify inputs and business rules |
| DLT grows after schema change | Consumer does not support new event version or deserializer is incompatible | Check schema compatibility, update consumer, and perform controlled replay |

## 14. Production design principles

When configuring not-retryable exceptions in Spring Kafka, follow these principles:

1. Classify by actual cause and recoverability, not merely by generic exception names.
2. Use `addNotRetryableExceptions` for data errors or deterministic errors that cannot be fixed by retrying.
3. Keep retryable and not-retryable lists clear; avoid overlapping classifications.
4. Preserve the original cause when wrapping exceptions and test cause traversal.
5. Configure a durable recoverer; for important data, prefer a DLT or quarantine suitable for investigation/replay.
6. Check DLT publish results and do not treat recovery as successful unless the record is persisted.
7. Separate business rejections from technical failures and invalid data errors.
8. Explicitly choose blocking retry (`DefaultErrorHandler`) or non-blocking retry (`@RetryableTopic`) according to ordering and latency needs.
9. For batch listeners, identify the exact failing record and design idempotent side effects.
10. Monitor classification, retries, DLT, consumer lag, and shifts across application versions.

Not-retryable exceptions stop the system from retrying errors that cannot be resolved by resending the same record. When classified accurately and paired with a recoverer capable of preserving records, consumers can keep processing the main stream while operations retain complete data to investigate, fix the root cause, and replay in a controlled manner.
