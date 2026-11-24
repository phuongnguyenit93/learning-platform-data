# Transient and Non-Recoverable Errors

When a consumer processes a Kafka record, an error may stem from a short-lived outage or from data/business rules that can never succeed if re-executed as-is. These two error groups require different handling. Transient errors can be retried with bounded attempts and wait times; non-recoverable errors should stop retrying early, record the cause, and be routed to a dead-letter topic (DLT), quarantine, or manual remediation workflow.

If you retry every error, a malformed record can occupy the consumer indefinitely, stalling the partition and increasing lag. If you never retry transient errors, even a brief database or dependency timeout can send a record to the DLT when waiting slightly longer would have allowed it to succeed. Therefore, the first step in designing error handling is classifying errors by root cause and recoverability.

## 1. Distinguishing Transient Errors from Non-Recoverable Errors

**Transient (retryable) errors** are errors likely to resolve once external conditions change: a dependent service is overloaded, a connection drops briefly, a database lock is held, or a downstream system applies temporary rate limiting. Re-executing the same operation after a reasonable wait can succeed.

**Non-recoverable (permanent/non-retryable) errors** are errors where retrying the same record, with the same data and the same conditions, will not improve the outcome. Examples include a payload missing a required field, an unsupported currency code, an invalid schema, or misconfigured access permissions. These errors require fixing the data, fixing configuration, or manual intervention.

| Criterion | Transient Error | Non-Recoverable Error |
|---|---|---|
| Likelihood of success on retry | Can increase after waiting or once the dependency recovers | Usually unchanged if record and configuration remain the same |
| Examples | DB timeout, HTTP 503, connection reset, temporary rate limit | Validation failure, invalid schema, unsupported currency, unparseable payload |
| Action | Retry with bounded backoff | Do not retry, or only retry under a data-fix policy; recover/DLT |
| Impact of prolonged retries | Increases latency and lag, though recovery is possible | Wastes resources and can block the partition |
| Remediation | Wait, shed load, recover dependency | Fix data, contract, permissions, or configuration; then replay in a controlled manner |

Classification must be based on the error's semantics in the specific system. An HTTP 404 may be permanent if the resource does not exist, yet transient if the request was sent before data finished synchronizing. A `DataAccessException` can cover both transient connection failures and unrecoverable SQL errors. Do not classify solely based on a generic exception name.

## 2. Causes That Are Typically Retryable

The following cases are generally safe to retry if business rules permit and the operation is idempotent:

- Timeouts when calling a database, HTTP service, or storage system.
- Connections closed/reset while a dependency is recovering.
- Database deadlocks or lock contention that may clear after a short wait.
- HTTP 429 (Too Many Requests) or 503 (Service Unavailable), provided a retry policy exists and `Retry-After` is respected when needed.
- Transient failures accessing object storage, caches, or internal services.
- Short-lived leader/network errors when calling another Kafka service or dependency.

Example listener calling an inventory service:

```java
@KafkaListener(topics = "orders.created", groupId = "order-worker")
public void onOrder(OrderCreated event) {
    try {
        inventoryClient.reserve(event.orderId(), event.items());
    } catch (InventoryUnavailableException ex) {
        throw new TransientInventoryException(
                "Inventory service is temporarily unavailable", ex);
    }
}
```

The application translates the dependency failure into a clearly named business exception. The error handler can classify `TransientInventoryException` as retryable. Wrapping exceptions lets the listener express operational intent instead of forcing the error handler to understand every low-level HTTP/DB exception.

Do not retry an error merely because it is a `RuntimeException`. Identify which dependencies can recover, their typical recovery times, and the consequences of re-running the operation.

## 3. Causes That Should Usually Not Be Retried

The following errors should usually stop retrying early:

- Data missing required fields or violating validation rules.
- Malformed JSON/XML/Avro or schema incompatibilities.
- Unsupported enum values, currencies, states, or business codes.
- Business rules definitively rejecting the operation, such as an order already canceled that cannot be paid.
- User or application lacking permissions due to invalid configuration or credentials.
- Misconfigured topic, endpoint, schema mapping, or application settings that cannot self-heal by waiting.
- Programming errors such as invalid null dereferences or invalid type casts.

Validation example:

```java
@KafkaListener(topics = "orders.created", groupId = "order-worker")
public void onOrder(OrderCreated event) {
    if (event.orderId() == null || event.items().isEmpty()) {
        throw new InvalidOrderException("Order must have an id and at least one item");
    }

    orderService.create(event);
}
```

If the data is invalid, retrying the same payload will keep failing. Send the record to a DLT along with error metadata so the owning team can inspect and fix the data. Once the root cause is resolved, records can be replayed from the DLT via a separate workflow.

Some configuration errors such as authentication or authorization failures can be resolved after updating secrets or ACLs. However, the consumer should not rapidly retry in a tight loop while configuration remains broken; it should fail fast, use a long backoff, or pause/stop the listener and alert according to operational policy.

## 4. Classify by Recoverability, Not Just Exception Name

An exception name is a technical signal, while the retry decision must also consider context:

| Situation | Retryable? | Reason |
|---|---|---|
| `SocketTimeoutException` when calling an internal service | Usually yes | The service may respond on a subsequent call |
| `SQLTransientConnectionException` | Usually yes | Connectivity may be restored |
| Database deadlock | Usually yes | Another transaction may release the lock |
| HTTP 429 | Yes, with backoff | Must respect rate limits and `Retry-After` |
| HTTP 503 | Usually yes | Service is temporarily unavailable or overloaded |
| HTTP 400 due to invalid payload | Usually no | Resending the payload will not fix the request |
| `MethodArgumentNotValidException` | Usually no | Data does not satisfy the contract |
| `ClassCastException` | No | Usually a data type or programming bug |
| `AuthenticationException` | Usually do not fast-retry | Credentials or authentication mechanism must be fixed |
| `IllegalStateException` | Depends on cause | Could be a transient state issue or a bug/configuration error |

Do not apply this table mechanically. For instance, HTTP 400 is occasionally returned by an API for a state that becomes retryable after prerequisite data arrives; HTTP 404 might merely reflect eventual consistency. Create specific business exceptions or map errors into outcomes with clear classification codes.

## 5. Retrying Does Not Mean Safe Re-execution

Retrying causes the listener to execute the same operation again. If the first attempt already wrote to a database or called an external service before the response timed out, the retry can produce duplicate side effects.

Example:

```text
Consumer receives OrderCreated
        |
        v
Call Payment API
        |
        v
Payment succeeded
        |
        v
Response timed out on the way back
        |
        v
Listener throws TransientPaymentException
        |
        v
Retry same record
        |
        v
Payment risks being created a second time
```

To make retries safe, use a stable idempotency key, typically the event ID or business operation ID:

```java
paymentClient.charge(
        event.paymentId(),       // stable idempotency key
        event.orderId(),
        event.amount());
```

Databases can also use a unique constraint on the event ID, an inbox table, or an upsert to prevent duplicate processing. Kafka offset commits and database transactions do not automatically provide exactly-once guarantees for side effects outside Kafka.

## 6. Where Does Retry Operate in Spring Kafka?

For a record listener, the listener container invokes the `@KafkaListener` method. If the method throws an exception, the container delegates the error to `CommonErrorHandler`. In modern Spring Kafka, `DefaultErrorHandler` is the standard implementation for classifying exceptions, performing backoff, seeking/retrying, and invoking a recoverer once attempts are exhausted.

High-level processing flow:

```text
poll() -> listener processes record
              |
              v
         Exception thrown?
          /       \
        No        Yes
         |          |
         v          v
processing complete  ErrorHandler classifies
                    |
              +-----+------+
              |            |
          Retryable    Non-retryable
              |            |
              v            v
        BackOff/retry   Recoverer immediately
              |
         retries left?
          /      \
        Yes      Exhausted
        |          |
        v          v
     reprocess   Recoverer/DLT
```

`DefaultErrorHandler` handles errors after the listener is invoked. Deserialization errors occurring before the listener receives the record require `ErrorHandlingDeserializer` to bring the exception into the container's error-handling path. Application startup errors, broker connectivity failures, or container configuration errors are also not always handled by the listener's error handler.

## 7. Default Exception Classification in DefaultErrorHandler

In modern Spring Kafka versions (2.8 and later), `DefaultErrorHandler` treats certain exceptions as fatal/non-retryable by default because retrying the same record is usually futile. Common defaults include:

- `DeserializationException`.
- `MessageConversionException`.
- `ConversionException`.
- `MethodArgumentResolutionException`.
- `NoSuchMethodException`.
- `ClassCastException`.

Other exceptions are typically treated as retryable by default, though applications should explicitly configure non-recoverable business errors. The default list may vary across versions; check the Spring Kafka documentation for your exact version before relying on default behavior.

One caveat: the listener container may wrap business exceptions inside a framework exception such as `ListenerExecutionFailedException`. When configuring a classifier, inspect the actual exception received by the handler and how the classifier traverses the cause chain. Log both the exception class and root cause to avoid misclassifying a non-retryable business error as retryable due to an outer wrapper.

## 8. Marking Non-Retryable Exceptions in DefaultErrorHandler

You can instantiate `DefaultErrorHandler` with a backoff and register non-retryable exceptions. Example:

```java
@Bean
public DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    ExponentialBackOffWithMaxRetries backOff =
            new ExponentialBackOffWithMaxRetries(4);
    backOff.setInitialInterval(1_000L);
    backOff.setMultiplier(2.0);
    backOff.setMaxInterval(10_000L);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(recoverer, backOff);

    handler.addNotRetryableExceptions(
            InvalidOrderException.class,
            UnsupportedCurrencyException.class,
            InvalidCustomerStateException.class);

    handler.addRetryableExceptions(
            TransientInventoryException.class,
            TransientPaymentException.class);

    return handler;
}
```

In this example, validation exceptions are forwarded straight to the recoverer. Transient inventory/payment errors are retried with exponential backoff. The values of 1 second, multiplier 2, and maximum 10 seconds are illustrative only; choose them based on dependency timeouts, SLAs, and allowable processing time.

`ExponentialBackOffWithMaxRetries(4)` caps the number of retries according to the corresponding Spring Framework/Spring Kafka API; total listener invocations consist of the initial attempt plus the retries. Verify how your version counts attempts and document it clearly in operational configuration to avoid confusion between "4 retries" and "4 total attempts".

Attach the handler to the container factory:

```java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        orderListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                DefaultErrorHandler kafkaErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
```

If Spring Boot auto-configures the default factory, you can customize the existing factory via a configurer or declare a dedicated factory bean. Ensure the listener references the right `containerFactory`; otherwise, the configured error handler may not apply to that endpoint.

## 9. Classifying with setClassifications

When you need to control both retryable and non-retryable entries in a single map, you can use `setClassifications(...)`:

```java
Map<Class<? extends Throwable>, Boolean> classifications = new HashMap<>();
classifications.put(InvalidOrderException.class, false);
classifications.put(UnsupportedCurrencyException.class, false);
classifications.put(TransientInventoryException.class, true);
classifications.put(TransientPaymentException.class, true);

handler.setClassifications(classifications, true);
```

A value of `true` means retryable; `false` means non-retryable. The second parameter is the default classification for unlisted exceptions. In the example, undeclared exceptions remain retryable. If you choose `false` as the default, you must declare every transient exception that needs retrying, or they will be recovered immediately.

`addRetryableExceptions(...)` and `addNotRetryableExceptions(...)` are usually easier to read when you only need to add a few exception types to the default policy. `setClassifications(...)` fits when you want to own the entire classification table. Avoid configuring multiple mechanisms simultaneously without checking override precedence.

Note: `setClassifications(...)` configures the classifier using the supplied map. If the default is set to `true`, framework exceptions that are fatal by default but absent from the map may also become retryable. When defining the full table yourself, include default non-retryable exceptions such as `DeserializationException`, `MessageConversionException`, `ConversionException`, `MethodArgumentResolutionException`, `NoSuchMethodException`, and `ClassCastException` with `false`; or use `addNotRetryableExceptions(...)` to preserve defaults and add only business types.

## 10. Choosing Backoff and Retry Limits

Retries must be bounded. Three common patterns:

| Backoff | Behavior | When Suitable |
|---|---|---|
| Fixed | Waits a fixed duration between attempts | Short-lived errors, stable latency |
| Exponential | Gradually increases wait time after each failure | Dependency recovering or under overload |
| Capped exponential | Increases gradually without exceeding a max interval | Want to reduce pressure while keeping wait times predictable |

Do not retry continuously with zero delay when a dependency is failing. That can cause a retry storm, overloading the dependent service further. For HTTP 429, you may need to respect `Retry-After`; in distributed systems with many consumers, jitter helps prevent all consumers from retrying at the exact same instant.

Total wait time must fit within `max.poll.interval.ms`, record processing budgets, and SLAs. Blocking retries hold the consumer thread during backoff; the partition cannot advance during that window. If long delays are required, consider retry topics/non-blocking retries instead of blocking the consumer thread for minutes.

## 11. Non-Retryable Does Not Mean Silently Dropping Records

When an error is determined to be non-recoverable, the system still needs a clear terminal action. Common options:

- Route the record to a dead-letter topic to preserve payload, key, headers, and error metadata.
- Write the record to a quarantine store if approval or data repair is needed before replay.
- Raise an alert and stop the container if the error indicates widespread configuration/system breakage.
- For business errors accepted as normal outcomes, return an intentional rejection state and commit per contract rather than throwing an exception.

Do not configure an exception as non-retryable and assume the record will automatically land in a DLT. `DefaultErrorHandler` requires an appropriate recoverer; with the default recoverer, behavior may simply log and mark the record recovered according to configuration. To publish to a DLT, configure `DeadLetterPublishingRecoverer` or a custom recoverer.

## 12. Sending Non-Recoverable Errors to a Dead Letter Topic

`DeadLetterPublishingRecoverer` can publish failed records to a DLT topic. By default, the destination is typically formed by appending `.DLT` to the original topic name and using the matching partition; ensure the DLT has enough partitions if preserving partition numbers.

Example configuring a custom destination:

```java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
                kafkaTemplate,
                (record, exception) -> new TopicPartition(
                        record.topic() + ".DLT",
                        record.partition()));
```

If the DLT lacks the corresponding partition, publishing can fail. You can pick another partition or have the partition resolver return `null` so the producer chooses a partition based on key/partitioner. Provision the DLT topic and verify replication factor, retention, ACLs, quotas, and serializers before enabling in production.

DLT records typically preserve source metadata such as original topic, partition, offset, timestamp, exception class, and exception message via headers added by Spring Kafka. Do not merely log a stack trace and drop the payload; the DLT must retain enough data for investigation and safe replay.

## 13. Deserialization Errors and Business Errors Need Different Paths

Deserialization errors happen when the Kafka client converts bytes into key/value objects. Since the listener has not been called yet, you cannot catch these with `try/catch` inside `@KafkaListener`. Spring Kafka provides `ErrorHandlingDeserializer` to preserve the exception and raw bytes in headers so the error handler/recoverer can handle them.

Example wrapping a JSON deserializer:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.orders.OrderCreated
        "[spring.json.trusted.packages]": com.example.orders
```

Malformed JSON is generally non-retryable if the payload will not change. A listener error due to a DB timeout can be retried. Distinguish these stages:

| Stage | Examples | Recommended Policy |
|---|---|---|
| Deserialization | Invalid bytes, corrupted JSON, incompatible schema | Non-retryable; DLT/quarantine |
| Message conversion | Cannot convert payload to listener parameter type | Usually non-retryable; DLT and check contract |
| Business validation | Missing order ID, negative amount | Non-retryable; DLT or business rejection |
| Dependency call | Database timeout, HTTP 503 | Bounded retries, then DLT |
| Programming error | `ClassCastException`, logic bug | Usually no blind retry; alert and DLT or stop depending on severity |

If a deserialization error happens on the key, handle the corresponding key exception header. When publishing to a DLT, the producer may need to support both deserialized payloads and raw `byte[]` stored in the exception header. Configure the DLT publisher's serializer to handle both types.

## 14. Blocking Retry vs. Non-Blocking Retry

Spring Kafka supports two main retry approaches:

**Blocking retry** uses `DefaultErrorHandler` to wait out backoff and retry the record on the consumer thread. This keeps retries close to the original partition and usually works well when retry counts are low and delays are short. During retry, the partition can be blocked, making subsequent records wait.

**Non-blocking retry** uses retry topics, typically configured via `@RetryableTopic` or `RetryTopicConfiguration`. Failed records are forwarded to a delayed retry topic and later consumed and retried by another listener. This frees the original topic's consumer sooner and suits long delays or workloads that must avoid blocking partitions.

Non-blocking retries alter processing order: newer records may be processed ahead of older records sitting in a retry topic. If business logic demands strict per-key ordering, weigh this carefully or keep blocking retries within bounded limits. Also check your Spring Kafka version and supported listener types before choosing retry topics.

Avoid accidentally stacking both retry mechanisms. If `DefaultErrorHandler` retries multiple times and `@RetryableTopic` also retries multiple times, total attempts and processing time can far exceed expectations.

## 15. Never Infinitely Retry Widespread System Outages

An error that looks transient on one record can be a symptom of a system-wide outage: database unreachable, expired credentials, or an overloaded downstream service. If all consumers retry relentlessly, the system can generate extra load and prolong the outage.

Combine these safeguards:

- Bounded max retry counts and capped backoff.
- Circuit breakers or rate limiters in dependency clients where appropriate.
- Explicit connection and request timeouts.
- Bounded concurrency to avoid overwhelming dependencies.
- Alerts when retry, DLT, or timeout rates spike abnormally.
- Pausing/stopping listeners per runbook when widespread configuration errors require intervention.

In particular, authentication/authorization errors will not heal with rapid retries. Service only resumes once secrets or ACLs are fixed. Detect these early and notify operations instead of burning through the entire retry budget for the same root cause.

## 16. Observing Retries and Error Classification

To verify whether your classifier behaves properly, monitor attempt counts and causes at every step:

- Total failed records by exception class and root cause.
- Retry counts before succeeding.
- Records recovered immediately as non-retryable.
- Records that exhausted retries and were published to the DLT.
- Actual backoff durations and time records spend in retry state.
- Consumer lag by topic/partition and listener processing duration.
- Error rates by dependency, HTTP status, SQL state, or business code.
- Failed DLT publishes and records awaiting manual remediation.

You can implement `RetryListener` on `DefaultErrorHandler` to observe retries and recovery:

```java
handler.setRetryListeners(new RetryListener() {
    @Override
    public void failedDelivery(ConsumerRecord<?, ?> record,
                               Exception exception,
                               int deliveryAttempt) {
        log.warn("Retry attempt={}, topic={}, partition={}, offset={}, cause={}",
                deliveryAttempt,
                record.topic(),
                record.partition(),
                record.offset(),
                exception.getClass().getSimpleName());
    }

    @Override
    public void recovered(ConsumerRecord<?, ?> record,
                          Exception exception) {
        log.error("Record recovered to DLT or alternate path: topic={}, partition={}, offset={}",
                record.topic(), record.partition(), record.offset());
    }
});
```

Callback APIs may offer additional overloads depending on the Spring Kafka version. In metrics, avoid high-cardinality labels such as event IDs, order IDs, or exception messages; use stable exception groups and topic names, and place specific IDs into controlled logs.

## 17. Testing Retryable vs. Non-Retryable Classification

Tests must prove both branches: transient errors are retried the expected number of times, and non-retryable errors go straight to the recoverer/DLT.

Minimum test scenarios:

| Scenario | Expectation |
|---|---|
| Listener throws `TransientInventoryException` then succeeds | Retries occur and the record is eventually processed |
| Listener always throws a transient exception | Retries up to the limit, then recovers/DLTs |
| Listener throws `InvalidOrderException` | Does not wait for retry backoff; routes to recoverer per configuration |
| Listener throws wrapper with non-retryable root cause | Classifier detects the right root cause per cause-traversal configuration |
| Deserializer encounters malformed JSON | Listener never receives invalid payload; error handler/recoverer handles the failed record |
| DLT broker/topic unavailable | Recovery publish failure is detected; record is not silently treated as successfully recovered |
| Dependency returns HTTP 429 | Backoff/rate limiting is applied per policy |
| Timeout after side effect completed | Retry does not create duplicate side effects thanks to idempotency |

With Embedded Kafka or Testcontainers, you can send records to a real topic, observe listener invocation counts, check committed offsets, and confirm records arrive in the DLT with source headers. Mock recoverers/backoffs in fast unit tests for the classifier, then run at least one integration test covering the full container flow.

## 18. Error Policy Design Workflow

1. List all dependencies and errors that can arise at each processing step.
2. Create dedicated business exceptions for transient and non-recoverable errors.
3. Determine whether retrying can make the operation succeed or merely repeat the same failure.
4. Audit side effects and add idempotency keys or unique constraints.
5. Configure `DefaultErrorHandler`, retryable/non-retryable classifiers, and bounded backoff.
6. Configure a recoverer/DLT for non-retryable errors or exhausted retries.
7. Define behavior when DLT publishing itself fails.
8. Test exception wrappers, deserialization errors, retry exhaustion, DLT routing, and duplicate delivery.
9. Monitor retry rates, lag, DLT volume, and processing latency to tune the policy.
10. Write runbooks for data repair, DLT replay, and widespread configuration errors.

## 19. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| Every `RuntimeException` should be retried | Must classify by root cause and recoverability |
| Non-retryable means dropping the message | Requires an explicit recoverer, DLT, quarantine, or business rejection |
| `DefaultErrorHandler` automatically sends all errors to a DLT | Requires configuring `DeadLetterPublishingRecoverer` or a custom recoverer |
| A successful retry means no duplicates | An earlier attempt may have caused side effects before timing out; idempotency is required |
| `auto.offset.reset` controls retries | That property handles invalid/missing offsets, not listener exception classification |
| Increasing retry counts always makes the system more reliable | Too many retries can stall partitions and trigger retry storms |
| HTTP 4xx is always permanent, 5xx is always transient | Must evaluate the API contract and business context |
| DLT publish failure does not affect progress | Unsuccessful recovery must be handled; verify error handler and recoverer behavior |
| Non-blocking retry preserves partition ordering | Retry topics allow newer records to be processed ahead of records waiting in retry |

## Pre-Production Error Handling Checklist

- Exceptions are classified by recoverability with clear business exception types.
- Validation, schema, and configuration errors are not blindly retried.
- Transient errors have bounded retry counts, backoff, and total wait time.
- The classifier has been tested against wrapped exceptions and actual root causes.
- `ErrorHandlingDeserializer` is used if deserialization errors must enter the error handler.
- Recoverer/DLT is explicitly configured; the DLT topic has suitable partitions, ACLs, and retention.
- The DLT publisher supports serializers for both valid payloads and raw bytes when needed.
- Idempotency is in place for repeatable side effects.
- Blocking retries do not exceed allowable processing/poll times; consider retry topics for long delays.
- Metrics/logs exist for retries, recovery, DLT routing, and DLT publish failures.
- Retry exhaustion, non-retryable routing, DLT failure, and replay have been tested.
- Runbooks exist for data repair, configuration fixes, and replaying records after root causes are resolved.

Transient and non-recoverable errors require two distinct policies. Bounded retries help weather brief disruptions; non-retryable classification and DLTs isolate bad data or unrecoverable business errors. When classifiers, backoff, recoverers, and idempotency are designed together, a Spring Kafka consumer can recover predictably without stalling partitions or causing unintended duplicate side effects.
