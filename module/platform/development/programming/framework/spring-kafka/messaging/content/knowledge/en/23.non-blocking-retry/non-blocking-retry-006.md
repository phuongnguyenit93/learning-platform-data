# Retrying Multiple Different Exceptions with Non-Blocking Retry

In Spring Kafka, non-blocking retry forwards failed records to retry topics instead of holding the consumer thread for backoff delays. `@RetryableTopic` supports classifying multiple exceptions: retrying only a chosen set of exceptions, skipping retries for another set, or inspecting exceptions nested inside the `cause` chain. When needed, the application can also route different error types to separate dead-letter topics (DLTs).

The key is distinguishing between two decisions:

- **Exception classification:** which exceptions are retried and which go straight to the DLT.
- **DLT routing:** when a record must go to a DLT, which DLT to select based on the exception that occurred.

These two decisions can work together, but they do not replace each other. For instance, `InvalidOrderException` might not be retried and go directly to `orders-validation-dlt`, whereas `InventoryUnavailableException` is retried several times before going to `orders-dependency-dlt`.

## 1. How Does Non-Blocking Retry Handle Exceptions?

When a listener throws an exception, Spring Kafka determines whether that exception belongs to the retryable group. If it is retryable and attempts remain, the record is published to the retry topic corresponding to the backoff interval. The retry consumer re-reads the record after the wait duration. If the exception is non-retryable or attempts are exhausted, the record is forwarded to the DLT as configured.

```mermaid
flowchart TD
    A[Main topic] --> B[@KafkaListener processes record]
    B --> C{Classify exception}
    C -->|Do not retry| D[Select DLT by exception]
    C -->|Retryable| E{Attempts remaining?}
    E -->|Yes| F[Publish to retry topic]
    F --> G[Retry consumer after backoff]
    G --> B
    E -->|No| D
    D --> H[DLT consumer / @DltHandler]
```

With non-blocking retry, the main topic consumer can continue processing subsequent records once the failed record is forwarded to the retry topic. This prevents a single failing record from blocking the entire partition, but can alter business processing order: later records may complete before a record awaiting retry.

## 2. Classifying Multiple Exceptions to Retry with include

`include` acts as an allowlist: only the declared exception types are retried according to the listener's policy. Other exceptions not in the allowlist skip retry topics and go directly to the DLT. This approach works well when the application only wants to retry a known set of transient errors.

Suppose an order service depends on inventory and pricing:

```java
class InventoryUnavailableException extends RuntimeException {
    public InventoryUnavailableException(String message) {
        super(message);
    }
}

class PricingServiceUnavailableException extends RuntimeException {
    public PricingServiceUnavailableException(String message) {
        super(message);
    }
}

class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}
```

Retry only the two transient dependency failures:

```java
@Component
public class OrderListener {

    @RetryableTopic(
            attempts = "4",
            backoff = @Backoff(
                    delay = 1_000,
                    multiplier = 2.0,
                    maxDelay = 10_000),
            include = {
                    InventoryUnavailableException.class,
                    PricingServiceUnavailableException.class
            },
            traversingCauses = "true"
    )
    @KafkaListener(
            topics = "orders",
            groupId = "order-projection"
    )
    public void onOrder(OrderCreated event) {
        orderService.process(event);
    }
}
```

In this example:

- `InventoryUnavailableException` and `PricingServiceUnavailableException` are retried.
- `InvalidOrderException` is not in the allowlist, so it goes straight to the DLT.
- `attempts = "4"` counts the initial processing attempt: one initial attempt plus up to three retries.
- Backoff increases exponentially: 1 second, 2 seconds, 4 seconds, capped at 10 seconds.
- `traversingCauses = "true"` allows searching for the declared exceptions within the `cause` chain.

According to current Spring Kafka documentation, `attempts` defaults to `3` (one initial attempt plus two retries), and the default backoff is a 1-second fixed delay. Declare these explicitly whenever the system policy needs clear review or stable testing.

## 3. Using exclude When You Want to Retry Most Exceptions

`exclude` acts as a denylist: declared exceptions are not retried and go straight to the DLT. All other exceptions are retried per policy, except those in Spring Kafka's global fatal exception list.

Example skipping retries for unrecoverable data errors:

```java
@RetryableTopic(
        attempts = "5",
        backoff = @Backoff(delay = 2_000),
        exclude = {
                InvalidOrderException.class,
                UnsupportedCurrencyException.class,
                CustomerNotFoundException.class
        },
        traversingCauses = "true"
)
@KafkaListener(topics = "orders", groupId = "order-projection")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
```

Choose `include` when only a few exceptions genuinely warrant retries and unknown errors should default to the DLT. Choose `exclude` when most errors are potentially transient and only a specific group of business errors should skip retries.

To keep policies readable, pick either an allowlist or a denylist strategy for each listener. If combining both `include` and `exclude`, check the classification rules for your active Spring Kafka version and write tests for overlapping cases; do not rely on assumptions about precedence between the two lists.

## 4. Classifying Multiple Exceptions with RetryTopicConfigurationBuilder

Beyond annotations, you can declare policies using `RetryTopicConfigurationBuilder`. This is useful when managing retry policies in a centralized configuration class and scoping them to specific topics.

```java
@Configuration
@EnableKafkaRetryTopic
public class OrderRetryConfiguration {

    @Bean
    public RetryTopicConfiguration orderRetryConfiguration(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {

        return RetryTopicConfigurationBuilder
                .newInstance()
                .includeTopics(List.of("orders"))
                .retryOn(List.of(
                        InventoryUnavailableException.class,
                        PricingServiceUnavailableException.class))
                .traversingCauses(true)
                .fixedBackOff(1_000L)
                .maxAttempts(4)
                .create(kafkaTemplate);
    }
}
```

In the builder:

- `retryOn(List.of(...))` declares multiple exceptions to retry.
- `notRetryOn(List.of(...))` declares multiple exceptions not to retry.
- `traversingCauses(true)` enables inspection of the cause chain.
- `includeTopics(...)` scopes the configuration to the `orders` topic.
- `fixedBackOff(...)` and `maxAttempts(...)` configure the retry schedule.

To use a denylist instead, replace `retryOn(...)` with:

```java
.notRetryOn(List.of(
        InvalidOrderException.class,
        UnsupportedCurrencyException.class))
```

When using a `RetryTopicConfiguration` bean, enable the retry-topic infrastructure as guided by your Spring Kafka version. `@EnableKafkaRetryTopic` is the common way to enable the infrastructure. If the application chooses to extend `RetryTopicConfigurationSupport` for global configuration, do not add `@EnableKafkaRetryTopic` at the same time; use only one of the two global configuration approaches.

## 5. Cause Traversal: Exceptions Wrapped Inside Another

In real-world applications, business exceptions are often wrapped by service-layer, proxy, or adapter exceptions. For example:

```java
try {
    inventoryClient.reserve(event.orderId());
}
catch (SocketTimeoutException exception) {
    throw new InventoryUnavailableException(
            "Inventory request timed out", exception);
}
```

The listener might wrap the exception further:

```java
try {
    orderService.process(event);
}
catch (InventoryUnavailableException exception) {
    throw new RuntimeException("Order processing failed", exception);
}
```

The resulting exception chain looks like:

```text
RuntimeException
  └── InventoryUnavailableException
        └── SocketTimeoutException
```

If the classifier only inspects the outermost exception, `include = InventoryUnavailableException.class` may fail to match `RuntimeException`. Enable cause traversal so the classifier searches for the exception type along the cause chain:

```java
@RetryableTopic(
        include = {InventoryUnavailableException.class},
        traversingCauses = "true"
)
@KafkaListener(topics = "orders")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
```

By default, Spring Kafka retries all exceptions without traversing causes when neither `include` nor `exclude` is configured. When an `include` or `exclude` list is declared, the current API enables cause traversal by default; however, setting `traversingCauses` explicitly ensures the policy does not depend on defaults or version differences.

Cause traversal only classifies exceptions. It does not unwrap, replace the thrown exception, or fix the underlying error. Preserve the cause via a constructor accepting `cause` when throwing new exceptions so both the classifier and logs have complete context.

## 6. Using includeNames and excludeNames

`@RetryableTopic` also supports `includeNames` and `excludeNames`, which accept exception class names as strings. This is useful when you want to avoid a compile-time dependency on an exception class, such as a class residing in an optional integration module.

```java
@RetryableTopic(
        includeNames = {
                "com.acme.inventory.InventoryUnavailableException",
                "com.acme.pricing.PricingServiceUnavailableException"
        },
        traversingCauses = "true"
)
@KafkaListener(topics = "orders")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
```

Class names must be fully qualified class names, exact in package and type name. A misspelled class name can prevent the exception from being classified as intended. When direct class references are possible, `include` and `exclude` are safer because the compiler checks the types.

## 7. Default Fatal Exceptions

Since Spring Kafka 2.8.3, non-blocking retry maintains a global list of fatal exceptions. These errors go straight to the DLT without generating retry attempts, because retrying generally cannot fix the root cause.

The default list referenced by Spring Kafka documentation from `DefaultErrorHandler` commonly includes:

- `DeserializationException`.
- `MessageConversionException`.
- `ConversionException`.
- `MethodArgumentResolutionException`.
- `NoSuchMethodException`.
- `ClassCastException`.

For example, if a payload cannot be deserialized into an object or the listener method cannot accept a compatible parameter type, resending the exact same bytes usually will not make the data valid. Routing the record to the DLT immediately avoids pointless retry loops.

The fatal list is a global classification layer independent of each listener's `include`/`exclude` policy. When investigating why an exception does not appear on a retry topic, check both the local classifier and the global fatal list.

## 8. Adding Exceptions to the Global Fatal List

If an exception type should go straight to the DLT across all listeners using non-blocking retry, you can add it to the global fatal list by extending `RetryTopicConfigurationSupport`:

```java
@Configuration
@EnableKafka
public class GlobalRetryConfiguration extends RetryTopicConfigurationSupport {

    @Override
    protected void manageNonBlockingFatalExceptions(
            List<Class<? extends Throwable>> nonBlockingFatalExceptions) {

        nonBlockingFatalExceptions.add(InvalidMessageContractException.class);
    }
}
```

For example, `InvalidMessageContractException` indicates an event violates its contract and cannot be fixed by waiting for a dependency to recover. Adding this exception to the fatal list sends records to the DLT without passing through retry topics.

Use global configuration only when the same rule applies across the entire non-blocking retry infrastructure. If only one listener requires a different policy, prefer `include` or `exclude` on that listener.

When using `RetryTopicConfigurationSupport`, there should be only one global configuration class extending it, following your active version's documentation for enabling infrastructure. Do not combine it with `@EnableKafkaRetryTopic`, as doing so may register duplicate infrastructure beans.

## 9. Routing Different Exceptions to Different DLTs

Retry classification answers the question "should it be retried?". `exceptionBasedDltRouting` answers the question "if the record must go to a DLT, which topic should receive it?". Exception-based DLT routing has been available since Spring Kafka 3.2.0.

Example separating validation errors and dependency errors:

```java
@RetryableTopic(
        attempts = "4",
        include = {
                InventoryUnavailableException.class,
                PricingServiceUnavailableException.class
        },
        traversingCauses = "true",
        exceptionBasedDltRouting = {
                @ExceptionBasedDltDestination(
                        suffix = "-validation",
                        exceptions = {InvalidOrderException.class}
                ),
                @ExceptionBasedDltDestination(
                        suffix = "-dependency",
                        exceptions = {
                                InventoryUnavailableException.class,
                                PricingServiceUnavailableException.class
                        }
                )
        }
)
@KafkaListener(topics = "orders", groupId = "order-projection")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
```

With main topic `orders` and default DLT suffix `-dlt`, the destinations can be:

| Final exception | Retried? | Target DLT |
|---|---|---|
| `InvalidOrderException` | No, because it is not in `include` | `orders-validation-dlt` |
| `InventoryUnavailableException` | Yes, until it succeeds or exhausts attempts | `orders-dependency-dlt` if attempts exhausted |
| `PricingServiceUnavailableException` | Yes, until it succeeds or exhausts attempts | `orders-dependency-dlt` if attempts exhausted |
| Other exception | No, because it is not in `include` | Default DLT `orders-dlt` |

The suffix declared in `@ExceptionBasedDltDestination` is placed before the general `dltTopicSuffix`. Routing only chooses the final DLT; it does not automatically add exceptions to the retryable list.

## 10. Handling the DLT with @DltHandler

You can declare a `@DltHandler` method in the same class as the listener to handle records that arrive at the DLT:

```java
@DltHandler
public void onOrderDlt(OrderCreated event) {
    dltService.storeForInvestigation(event);
}
```

If no `@DltHandler` is declared, Spring Kafka creates a default DLT consumer that merely logs the record. In production, define clearly whether DLT records will be persisted, alerted on, turned into tickets, or queued for a replay workflow.

If multiple exception-specific DLTs exist, the handler needs a way to identify the error source or use separate listeners per DLT topic. Do not store only the payload while discarding exception metadata, original topic, partition, offset, and delivery attempt count.

## 11. Multiple Exceptions Do Not Mean Multiple Retry Topics

Exceptions classified via `include`/`exclude` normally share the listener's retry topology and backoff schedule. Having three retryable exceptions does not automatically create three separate retry topic chains.

If different error groups need different retry schedules, you can:

- Split listeners or topics by business group so each group has an independent policy.
- Use multiple `RetryTopicConfiguration` beans with clear topic scopes.
- Use a custom backoff policy if delays must be decided dynamically per record/exception and your API version supports it.
- Separate DLTs by exception via `exceptionBasedDltRouting` when only the final storage destination differs.

Avoid creating a huge list of exceptions with confusing implicit retry behaviors. Group errors by recoverability: transient dependency failures, rate-limit errors, data errors, and contract errors.

## 12. Classifying Exceptions by Business Nature

A practical policy might classify errors as follows:

| Error category | Examples | Recommended policy |
|---|---|---|
| Transient dependency | `InventoryUnavailableException`, `PricingServiceUnavailableException` | Retry with exponential backoff |
| Rate limit | `PartnerRateLimitException` | Retry with sufficiently long delay per quota or `Retry-After` if integrated |
| Invalid data | `InvalidOrderException`, `UnsupportedCurrencyException` | Do not retry; route to DLT for investigation |
| Incompatible contract/schema | `InvalidMessageContractException` | Typically route straight to DLT |
| Unknown programming bug | `NullPointerException`, invariant violation | Evaluate retrying carefully; usually should not loop indefinitely |

Do not classify purely by exception name. For example, `IllegalStateException` might indicate an unready dependency in one system yet an invariant bug in another. Create meaningful domain exceptions and preserve their causes.

## 13. Interaction with Blocking Retry and DefaultErrorHandler

Non-blocking retry routes records through retry topics; blocking retry holds records at the consumer and retries via an error handler such as `DefaultErrorHandler`. The two mechanisms can be combined in certain configurations, but you must clarify which layer handles exceptions first and which exceptions are forwarded.

When strict ordering within a partition is required, blocking retry generally preserves order more easily because the failing record continues holding subsequent records in that partition. Non-blocking retry lets the main consumer move on, so later records can be processed before the retrying record.

Do not apply the same exception classifier across multiple layers without testing. If `DefaultErrorHandler` retries first before handing the exception to non-blocking retry, total delivery attempts may differ from the `attempts` observed at the retry-topic layer.

## 14. Limitations of Non-Blocking Retry

Spring Kafka does not support non-blocking retry with batch listeners and cannot combine non-blocking retry with container transactions. If a listener requires batch mode or container-managed transactions, choose an appropriate alternative error-handling mechanism, such as `DefaultErrorHandler`/`DeadLetterPublishingRecoverer` for batches or `AfterRollbackProcessor` for transactions.

Non-blocking retry can also alter processing order because failed records are routed to another topic while the main topic continues consuming. If event ordering is a business invariant, evaluate carefully before choosing this retry topology.

## 15. Testing the Exception Classifier

Test every classification branch rather than verifying only that one exception is retried:

1. An exception in `include` is forwarded to a retry topic.
2. An exception outside `include` goes straight to the DLT.
3. An exception in `exclude` goes straight to the DLT.
4. An exception outside `exclude` is retried.
5. An exception nested inside a cause is matched when `traversingCauses=true`.
6. The same nested cause exception does not match when cause traversal is disabled, if policy requires verifying that distinction.
7. Global fatal exceptions go straight to the DLT without retries.
8. Exceptions are routed to the expected DLT suffix per `exceptionBasedDltRouting`.
9. After exhausting `attempts`, the record lands in the default DLT or the exception-specific DLT.
10. The DLT handler stores payload and metadata for investigation.

You can use `@EmbeddedKafka` or Testcontainers Kafka. Send events with unique IDs per test, await retry/DLT arrival using Awaitility or timeout-bounded polling, and assert which topics receive the records. Do not rely on fixed `Thread.sleep` calls because backoff, broker scheduling, and consumer startup can vary timing.

Test cases should count listener invocations and verify the final record on the retry topic/DLT. Also check metadata such as original topic, partition, offset, and exception headers to ensure post-failure investigation workflows function properly.

## 16. Common Pitfalls

**Declared include, yet the exception still goes to DLT:** check whether the actual thrown exception matches the declared type, whether it is wrapped in a cause, and whether `traversingCauses` is enabled.

**Declared exclude, yet the exception still retries:** inspect the cause chain, the actual thrown class, and the active retry topic configuration applied to the listener/topic.

**Exception not in include, yet expected to retry:** an allowlist retries only the specified types; use `exclude` if you want to retry most exceptions.

**Forgetting global fatal exceptions:** certain deserialization/conversion errors are routed straight to the DLT despite a general listener retry policy.

**Enabled cause traversal, yet the exception still fails to match:** a wrapper exception might not preserve the cause, or the actual runtime class differs from the declared class. Log the full exception chain.

**Typo in includeNames:** use the exact fully qualified class name; prefer class literals whenever possible.

**Assuming exceptionBasedDltRouting enables retries:** this feature only selects the target DLT, while `include`/`exclude` and the fatal classifier decide whether to retry.

**Multiple listeners on one topic using different policies:** Spring Kafka applies a single retry configuration per topic; listeners sharing a topic should align their configuration.

**Using non-blocking retry with batch or container transactions:** neither case is supported. Choose an appropriate error-handling strategy.

**Lost business ordering:** the main consumer continues processing subsequent records while an earlier record sits in a retry topic. Evaluate partition keys and ordering requirements.

## 17. Production Checklist

- Chose allowlist `include` or denylist `exclude` based on error characteristics.
- Exception lists use specific classes with domain-meaningful names.
- Decided whether `traversingCauses` is needed and configured it explicitly.
- Reviewed the global fatal exceptions list.
- Understood `attempts` as total attempts, including the initial processing attempt.
- Backoff aligns with SLAs, dependency recovery times, and external quotas.
- If using multiple DLTs, each suffix has a corresponding consumer or handling workflow.
- `@DltHandler` or the DLT consumer persists payload and investigation metadata.
- Retry topic configuration is scoped properly to topics without conflicts across listeners.
- Assessed ordering impacts when the main topic continues processing subsequent records.
- Not using non-blocking retry with batch listeners or container transactions.
- Tests cover `include`, `exclude`, nested causes, fatal exceptions, exhausted attempts, and DLT routing.
- Metrics/logs track retry attempts, DLT counts, exception types, and retry/DLT publish failures.

## References

- [Spring Kafka – Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html)
- [Spring Kafka – Retry Features and Exception Classifier](https://docs.spring.io/spring-kafka/reference/retrytopic/features.html)
- [Spring Kafka – Retry Configuration](https://docs.spring.io/spring-kafka/reference/retrytopic/retry-config.html)
- [Spring Kafka – Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
