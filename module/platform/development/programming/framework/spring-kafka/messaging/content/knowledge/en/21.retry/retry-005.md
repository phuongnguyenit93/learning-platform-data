# Skipping Non-Retryable Exceptions

Retries help consumers ride out transient failures, such as a partner service timing out or a database momentarily dropping connections. However, retrying an event with an invalid payload, missing required fields, or an unsupported format rarely improves the situation. Every retry only adds latency, consumes consumer resources, and can delay valid records behind it.

In Spring Kafka, you can classify exceptions so `DefaultErrorHandler` skips retries for errors known to be unrecoverable on their own. Skipping retries does not mean silently discarding the record: the error handler still routes the record to the configured recovery path, such as logging or publishing to a dead-letter topic (DLT).

## 1. Distinguishing Transient Errors from Non-Retryable Errors

Retry decisions should be based on business root causes and whether the error can resolve itself, not merely on whether the exception is checked or unchecked.

| Error group | Examples | Typically appropriate handling |
| --- | --- | --- |
| Transient | Partner service timeout, brief database disconnect, HTTP 503, temporary lock | Bounded retry with backoff; then recover if still failing |
| Permanent (unrecoverable via retry) | Payload missing required field, unsupported event type, unreadable schema version, fixed data rule violation | Do not retry; record reason and route to DLT or error store |
| Business-state dependent | Order not ready because another event has not arrived yet, resource temporarily locked | Determine if the error clears over time or needs another event; pick bounded retry or an appropriate compensation flow |

For example, `InvalidOrderException` can represent invalid order data and should not be retried. Conversely, `PartnerServiceUnavailableException` can represent a partner service that is temporarily unavailable and should be retried. Create exceptions with clear business semantics so policies do not rely on overly broad types like `RuntimeException`.

## 2. How DefaultErrorHandler Decides Whether to Retry

`DefaultErrorHandler` is the `CommonErrorHandler` implementation commonly used for record listeners. When a listener throws an exception, the handler classifies it and either applies `BackOff` or calls the recoverer:

1. If the exception is classified as retryable, the handler waits per `BackOff` and redelivers the record according to the retry policy.
2. If the exception is classified as not retryable, the handler skips retry attempts and invokes the recoverer immediately on that failure.
3. Once a retryable exception exhausts its attempts, the recoverer is likewise called to handle the record that cannot proceed.

Modern Spring Kafka versions preconfigure certain technical exceptions as fatal, meaning they are not retried by default. This group typically includes `DeserializationException`, `MessageConversionException`, `ConversionException`, `MethodArgumentResolutionException`, `NoSuchMethodException`, and `ClassCastException`. The default list can vary across versions; check your dependency's documentation before relying on it.

Applications can add business exceptions to the not-retryable list. This is the right choice when you know that redelivering the exact same record cannot resolve the failure.

## 3. Declaring Non-Retryable Exceptions

`DefaultErrorHandler` provides `addNotRetryableExceptions(...)` to mark one or more exception types as non-retryable. The following example sends failed records straight to the DLT upon encountering any of the declared business errors:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
    var handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));

    handler.addNotRetryableExceptions(
            InvalidOrderException.class,
            UnsupportedEventVersionException.class);

    return handler;
}
```

In this example:

- `InvalidOrderException` and `UnsupportedEventVersionException` go straight to the recoverer without waiting one second or retrying twice.
- Other retryable exceptions use `FixedBackOff(1_000L, 2L)`: waiting one second between attempts with at most two retries after the initial processing attempt.
- `DeadLetterPublishingRecoverer` uses `KafkaTemplate` to publish unrecoverable records to the DLT per the recoverer's routing rules.

Register the handler on the listener container factory so listeners using that factory share the policy:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultErrorHandler orderErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(orderErrorHandler);
    return factory;
}
```

Listeners use that factory via the `containerFactory` attribute of `@KafkaListener`. Bean names, key/value types, and deserializer settings must match the actual application.

## 4. Not Retrying Does Not Mean Silently Dropping Records

Not-retryable classification only decides not to re-run the listener via `BackOff`. Afterward, the recoverer is responsible for handling the failed record. You can choose among the following approaches:

- Send the record and error metadata to a DLT so operators can inspect, repair data, or replay after fixing the issue.
- Persist to a durable error store if the application has its own management and recovery workflow.
- Use a logging recoverer when records only need to be recorded under an accepted policy; ensure logs contain enough detail for traceability.

In business systems, a DLT is usually more useful than logging alone because it retains the record for investigation and later handling. Ensure the target topic exists, has a partition count matching your routing strategy, and that the producer has write permissions. Headers containing exception class, message, topic, partition, offset, and timestamp can be included to ease troubleshooting.

When the recoverer sends to the DLT successfully, the error handler considers the record recovered and the container continues per the configured commit/acknowledgment policy. If sending to the DLT fails, recovery is incomplete; monitor this failure and design an appropriate redelivery policy. Never treat invoking a recoverer as a guarantee that the record was safely stored.

## 5. Choosing Specific Exceptions and Handling Wrapped Exceptions

Declare narrow exception types that clearly represent non-retryable errors. Avoid configuring broad classes such as `Exception`, `RuntimeException`, or `IllegalStateException` if they can also represent transient errors in the application.

For example, if `IllegalArgumentException` is used both for invalid input data and for misconfigured internal parameters, marking the entire type as not retryable could mask a code bug. A dedicated business exception makes the policy clearer:

```java
public class InvalidOrderException extends RuntimeException {

    public InvalidOrderException(String message) {
        super(message);
    }
}
```

Classifiers typically evaluate exception types via inheritance. However, listeners, adapters, or integration layers may wrap the original error inside another exception. When that happens, inspect the actual exception passed to the error handler and check how your Spring Kafka version traverses the `cause` chain. Do not assume a nested exception is classified the same way as when thrown directly; test wrapped cases as well.

If an exception treated as fatal by default can actually be retried in a specific business flow, `DefaultErrorHandler` also supports `addRetryableExceptions(...)` to add retryable classifications. Use this only when you have confirmed the error can self-heal and set an appropriate retry cap.

## 6. Relationship with KafkaListenerErrorHandler

`KafkaListenerErrorHandler` runs at the adapter level of a single `@KafkaListener`, whereas `DefaultErrorHandler` manages errors at the container level. If a listener error handler catches an exception and returns normally, the adapter treats the error as handled and the container never receives that exception for retry classification. Therefore:

- To let `DefaultErrorHandler` skip retries and invoke the recoverer for a non-retryable exception, the listener error handler must rethrow the exception.
- Return normally only when the listener error handler has performed durable recovery and intentionally accepts not retrying that record.

Never swallow an exception just to avoid retries. Doing so can acknowledge the offset even though the event was neither processed nor saved to any recovery destination.

## 7. Non-Blocking Retry with Retry Topics

If the application uses the retry-topic mechanism (`@RetryableTopic`), configure the excluded exception list appropriately for your Spring Kafka version. The annotation supports the `exclude` attribute in versions with the corresponding retry-topic feature:

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 1_000L),
        exclude = {
                InvalidOrderException.class,
                UnsupportedEventVersionException.class
        })
@KafkaListener(topics = "${app.kafka.orders-topic}")
public void onOrder(OrderCreated event) {
    orderService.handle(event);
}
```

Exceptions in `exclude` are not routed through the retry topic chain. Check your Spring Kafka version and the active `include`/`exclude` policy, as retry topics have a classification mechanism separate from `DefaultErrorHandler`. Do not configure conflicting retry policies on the same stream.

## 8. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Retrying unchangeable validation errors | Wastes time, grows backlog | Mark the business exception not retryable and send to DLT |
| Marking `RuntimeException` as not retryable | Transient errors skip retries | Use dedicated exceptions for permanent errors |
| Assuming not retryable means auto-deleting records | Nowhere to retain records for investigation or recovery | Configure an explicit recoverer, usually a DLT |
| Listener error handler catches and returns normally | Container never sees the error to classify | Rethrow the exception if container recovery is desired |
| Ignoring exception wrappers | Classification does not match the actual failure | Check exception type and cause; test wrapped exceptions |
| DLT write fails yet record is treated as safe | Risk of losing the recovery path | Monitor recoverer failures and verify failure behavior |

## 9. Testing Not-Retryable Policies

Tests should verify listener invocation counts and where the record ends up, rather than just checking whether an exception appeared in logs.

1. Send a record triggering `InvalidOrderException`; verify the listener is invoked only once and the record reaches the configured DLT.
2. Send a record triggering `PartnerServiceUnavailableException`; verify the listener is retried according to the `BackOff` count and intervals.
3. Send a business exception nested inside a wrapper; verify the classifier handles it as configured under your version's cause traversal settings.
4. Force the DLT producer to fail; verify the recovery error is observed and the record is not unintentionally marked as recovered.
5. Inspect DLT headers and metadata to confirm source topic, partition, offset, and root cause can be identified.

## 10. Implementation Checklist

- [ ] Errors are classified by self-healing capability, not solely by checked/unchecked exception.
- [ ] Non-retryable business exceptions have dedicated types whose names express the root cause.
- [ ] `DefaultErrorHandler.addNotRetryableExceptions(...)` is configured on the handler used by the listener container.
- [ ] BackOff applies only to retryable error groups and has appropriate limits.
- [ ] The recoverer has well-defined behavior; the DLT exists and has necessary write permissions if used.
- [ ] Verified how the classifier handles inherited and wrapped exceptions.
- [ ] `KafkaListenerErrorHandler` does not accidentally swallow exceptions intended for container handling.
- [ ] For retry topics, `exclude` is configured separately and compatible with your Spring Kafka version.
- [ ] Tested listener invocation counts, recovery results, DLT headers, and DLT publish failures.

A sound policy gives transient failures a chance to recover while routing unfixable data errors promptly into a dedicated workflow. This keeps consumers from looping fruitlessly on the same record and allows subsequent valid events to keep flowing.
