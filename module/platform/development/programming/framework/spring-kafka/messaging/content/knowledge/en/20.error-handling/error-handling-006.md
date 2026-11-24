# ExceptionClassifier

When a `@KafkaListener` throws an exception, Spring Kafka needs to decide whether to retry processing the record or go straight to a recovery step such as sending it to a dead-letter topic (DLT). Retrying every exception under the same policy is rarely effective: a transient timeout may heal on its own, whereas a malformed payload or business-rule violation will keep failing no matter how many times it is retried.

`ExceptionClassifier` provides a mechanism to classify exceptions into retryable and non-retryable groups. Error handlers like `DefaultErrorHandler` use this classification result to decide whether to apply backoff/retry or invoke the recoverer. Understanding the classifier helps you tailor retries to the nature of each error, avoiding wasted retries and preventing recoverable records from being skipped prematurely.

## 1. What Problem Does ExceptionClassifier Solve?

Suppose a consumer processes payment events. Different errors can occur during processing:

| Exception | Cause | Typically Appropriate Policy |
|---|---|---|
| `SocketTimeoutException` | Dependent service responds slowly temporarily | Bounded retries with backoff |
| `TransientDataAccessException` | Database temporarily unreachable | Bounded retries |
| `InvalidPaymentException` | Invalid business data | Do not retry; route to DLT or handle manually |
| `IllegalArgumentException` | Invalid payload or argument | Usually do not retry |
| `DeserializationException` | Cannot convert bytes into expected data type | Usually do not retry until data or schema is fixed |

If every error is retried, the consumer can hold up a partition too long over a single unprocessable record. If no errors are retried, a brief network blip can send records to the DLT prematurely.

A classifier lets the application express clear rules: transient errors get retried; unrecoverable data or business errors go to the recoverer.

## 2. How Do Classifier, Error Handler, Backoff, and Recoverer Differ?

Error-handling components each have distinct responsibilities:

| Component | Responsibility |
|---|---|
| `ExceptionClassifier` | Classifies an exception as retryable or non-retryable |
| `DefaultErrorHandler` | Coordinates record listener error handling, retries, and record recovery |
| `BackOff` | Determines wait intervals and retry attempt counts |
| `ConsumerRecordRecoverer` | Handles the record after retries are exhausted or for non-retryable exceptions |
| `DeadLetterPublishingRecoverer` | A common recoverer that publishes failed records to a DLT |

The classifier does not re-invoke the listener itself, nor does it send records to the DLT. It solely supplies the classification decision to the error handler. The error handler combines that decision with backoff and a recoverer to take action.

```text
@KafkaListener processes record
          |
          +---- success -----------------------> continue / commit per AckMode
          |
          +---- throws exception
                    |
                    v
             ExceptionClassifier
                    |
             +------+------+
             |             |
         Retryable     Non-retryable
             |             |
             v             v
          BackOff       Recoverer
             |             |
          Seek/retry       DLT or other handling
             |
       Retries exhausted and still failing
             |
             v
          Recoverer
```

## 3. How Spring Kafka Classifies Exceptions

In Spring Kafka, `org.springframework.kafka.listener.ExceptionClassifier` provides the classification logic used by error handlers. `DefaultErrorHandler` has a default policy: most exceptions are considered retryable, while several errors indicating the record cannot be fixed by retrying are considered fatal/non-retryable. Methods such as `addRetryableExceptions()` and `addNotRetryableExceptions()` are inherited to configure the policy.

Default exceptions commonly categorized as fatal include:

- `DeserializationException`.
- `MessageConversionException`.
- `ConversionException`.
- `MethodArgumentResolutionException`.
- `NoSuchMethodException`.
- `ClassCastException`.

The default list can vary across Spring Kafka versions. Check the Javadoc/documentation for your project's version when relying on the exact list. You can extend or override classifications according to your application's rules.

### Marking Exceptions Non-Retryable

For instance, invalid order data cannot become valid simply by running the listener again:

```java
public class InvalidOrderException extends RuntimeException {

    public InvalidOrderException(String message) {
        super(message);
    }
}
```

Assuming `recoverer` has already been created, add this exception to the handler's non-retryable set:

```java
import java.net.SocketTimeoutException;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

var errorHandler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 3L)
);

errorHandler.addNotRetryableExceptions(
        InvalidOrderException.class,
        IllegalArgumentException.class
);
```

If the listener throws `InvalidOrderException`, the error handler skips normal retries and forwards the record to the recoverer. For other exceptions not classified as non-retryable, the handler continues applying its default policy and backoff.

### Marking Exceptions Retryable

Certain business or infrastructure errors can be explicitly marked by the application as transient:

```java
public class InventoryTemporarilyUnavailableException extends RuntimeException {

    public InventoryTemporarilyUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Register the exception in the same handler's retryable set:

```java
errorHandler.addRetryableExceptions(
        InventoryTemporarilyUnavailableException.class,
        SocketTimeoutException.class
);
```

This is useful when an exception belongs to the default fatal list yet the application has a specific reason to retry it, or when you want to document policy explicitly for key transient errors. Do not mark an exception retryable just to avoid the DLT; verify the error can self-heal and set suitable retry bounds.

## 4. Full Configuration with DefaultErrorHandler and DLT

The following example uses `DeadLetterPublishingRecoverer` to route records to a DLT when an error is non-retryable or retry attempts are exhausted:

```java
import java.net.SocketTimeoutException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
class KafkaErrorHandlingConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
        var backOff = new FixedBackOff(1_000L, 3L);
        var handler = new DefaultErrorHandler(recoverer, backOff);

        handler.addRetryableExceptions(
                InventoryTemporarilyUnavailableException.class,
                SocketTimeoutException.class
        );
        handler.addNotRetryableExceptions(
                InvalidOrderException.class,
                IllegalArgumentException.class
        );

        return handler;
    }
}
```

Attach the error handler to the listener container factory:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;

@Configuration
class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            kafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory,
                    DefaultErrorHandler kafkaErrorHandler) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(kafkaErrorHandler);
        return factory;
    }
}
```

Listener using this factory:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {

    @KafkaListener(
            topics = "orders.events",
            groupId = "order-projection",
            containerFactory = "kafkaListenerContainerFactory"
    )
    public void consume(OrderEvent event) {
        orderService.process(event);
    }
}
```

The example assumes the application already defines `OrderEvent`, `orderService`, `InvalidOrderException`, `InventoryTemporarilyUnavailableException`, and the corresponding serializer/deserializer beans. `FixedBackOff(1_000L, 3L)` waits one second between retries and allows up to three retries after the initial processing attempt. If it still fails, the recoverer is invoked.

If the application uses a custom factory for a listener, attach `CommonErrorHandler` to the exact factory used by that listener. Creating a `DefaultErrorHandler` bean that the container never references will not change how the listener handles errors.

## 5. How ExceptionClassifier Handles Nested Exceptions

Spring Kafka can wrap exceptions from the listener inside another exception, such as `ListenerExecutionFailedException`. The original exception may lie inside the `getCause()` chain:

```text
ListenerExecutionFailedException
  └── InventoryTemporarilyUnavailableException
        └── SocketTimeoutException
```

If classification rules need to inspect the cause chain, you can configure the classifier to traverse causes:

```java
errorHandler.setTraverseCauses(true);
```

When traversal is enabled, the classifier can locate registered exceptions anywhere in the cause chain instead of inspecting only the outermost exception. Check the default behavior and API of your Spring Kafka version; explicit configuration avoids relying on assumptions about wrapping.

Cause-based classification is especially helpful when database libraries or HTTP clients wrap the underlying exception in a business exception. However, avoid classifying an overly broad cause if that same cause can appear in both transient and unrecoverable errors.

## 6. Classification by Exception Type and Inheritance

Classification rules can apply to an exception class and its subclasses per Spring's exception classification mechanism. For example, if `InvalidOrderException` is the parent class of multiple data errors, registering the parent class applies the same policy to the entire group.

```java
public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}

class MissingOrderIdException extends InvalidOrderException {
    public MissingOrderIdException() {
        super("orderId is required");
    }
}
```

Registering `InvalidOrderException.class` in the non-retryable group applies to `MissingOrderIdException` as well under superclass/subclass classification rules. This keeps the policy concise when you have a family of business exceptions.

When exception classes have complex inheritance hierarchies, write classification tests to verify which class takes precedence. Avoid registering the same class or parent/child classes into opposing groups because the outcome becomes hard to read and fragile during refactoring.

## 7. Classification and Retry Counts Are Two Separate Decisions

The classifier only answers whether an exception is retryable. Backoff decides how many times to retry and how long to wait.

Example:

```java
import java.net.SocketTimeoutException;

// Assume recoverer has already been created and passed to the handler.
var backOff = new FixedBackOff(2_000L, 4L);
var handler = new DefaultErrorHandler(recoverer, backOff);

handler.addNotRetryableExceptions(InvalidOrderException.class);
handler.addRetryableExceptions(SocketTimeoutException.class);
```

For `SocketTimeoutException`, the handler can perform up to four retries, waiting two seconds between attempts. For `InvalidOrderException`, the handler skips backoff waiting and invokes the recoverer immediately. A retryable exception can still be recovered once retry attempts are exhausted.

| Classification | BackOff | Outcome |
|---|---|---|
| Retryable | Attempts remaining | Wait and retry via error handler mechanism |
| Retryable | Attempts exhausted | Invoke recoverer |
| Non-retryable | No retry applied | Invoke recoverer immediately |

Choose backoff based on the dependency's expected recovery time. Retrying too aggressively can overload an already struggling system further; retrying too slowly can stall the partition and increase consumer lag.

## 8. ExceptionClassifier and Deserialization Errors

Deserialization happens before the listener receives the payload. If the consumer cannot deserialize bytes, the `@KafkaListener` method may never be called. To let the Spring Kafka error handler process this kind of error, you typically need `ErrorHandlingDeserializer` wrapping the actual deserializer.

JSON consumer example:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.events.OrderEvent
        spring.json.trusted.packages: com.example.events
```

`ErrorHandlingDeserializer` stores deserialization error details in headers so the listener container/error handler can recognize and process the corrupted record. `DeserializationException` usually belongs to the default fatal group because retrying the same bytes with the same deserializer will not make the payload valid.

If the error stems from an incompatible producer/consumer schema or version, fix the contract or serializer/deserializer configuration before replaying the record. You can route the failed record to a DLT for investigation and later handling.

## 9. ExceptionClassifier with Retry Topics

`DefaultErrorHandler` and `@RetryableTopic` are two distinct retry orchestration mechanisms. Classifications configured on `DefaultErrorHandler` do not automatically become rules for retry topics.

For non-blocking retries, you can declare included and excluded exceptions directly on the annotation:

```java
import java.net.SocketTimeoutException;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
class PaymentListener {

    @RetryableTopic(
            attempts = "4",
            backoff = @Backoff(delay = 1_000, multiplier = 2.0),
            include = {SocketTimeoutException.class},
            exclude = {InvalidPaymentException.class}
    )
    @KafkaListener(topics = "payments.events", groupId = "payment-projection")
    public void consume(PaymentEvent event) {
        paymentService.process(event);
    }
}
```

This example assumes `PaymentEvent`, `paymentService`, and `InvalidPaymentException` are already declared in the application. It illustrates a retry topic policy: timeouts pass through retry topics, while business data errors are excluded from retries. When using `@RetryableTopic`, check your Spring Kafka version, retry/DLT topic naming, total attempt count, and batch/transaction constraints to configure properly.

## 10. Classification in Transactional Listeners

When a container uses Kafka transactions, an exception from the listener can cause the transaction to roll back. Post-rollback error handling is normally coordinated by `AfterRollbackProcessor` or `DefaultAfterRollbackProcessor`, rather than directly reusing the non-transactional `DefaultErrorHandler` flow.

After-rollback error processors also support exception classification in the Spring Kafka hierarchy. Similar retryable/non-retryable rules can be applied, but they must be configured on the actual processor used by the container. Do not assume that configuring a `DefaultErrorHandler` automatically governs every transaction rollback.

When using transactions, clarify:

- Which exceptions trigger transaction rollback.
- How many retry attempts occur before recovery.
- Whether the recoverer publishes to the DLT within an appropriate transaction.
- Which transaction commits the offset.
- Whether external side effects outside Kafka have separate coordination or require idempotency.

Kafka transactions do not automatically span databases or HTTP services. If a listener updates a database, use an inbox/outbox pattern or a transaction coordination strategy matching your architecture.

## 11. Testing ExceptionClassifier Rules

Classification should be tested independently from business logic to avoid misconfigurations that retry or drop records improperly. You can instantiate the handler in a test and assert classification results using the API of your Spring Kafka version.

In addition to unit tests, include integration tests with Embedded Kafka or a test broker to verify actual behavior:

1. A retryable exception causes the listener to be re-invoked the configured number of times.
2. A non-retryable exception skips backoff and is recovered per policy.
3. Exceptions nested in the cause chain are classified as intended when traversal is enabled.
4. The recoverer publishes to the DLT successfully before the source offset is acknowledged.
5. A DLT publish failure does not falsely mark the source record as recovered.
6. Deserialization errors are routed to the error handler when `ErrorHandlingDeserializer` is used.
7. The consumer continues processing subsequent records once the failing record is recovered.

When testing retries, record the actual listener invocation count and wait durations. Avoid checking only logs, since logs do not prove the offset committed or the DLT received the record.

## 12. Exception Classification Design Workflow

A practical workflow can follow these steps:

1. Inventory exceptions from listeners, serializers/deserializers, databases, and external services.
2. Identify which errors can self-heal after waiting or retrying.
3. Mark data errors, unrecoverable business errors, and configuration errors as non-retryable.
4. Identify exceptions wrapped in cause chains and enable traversal if needed.
5. Choose appropriate backoff, retry counts, and total time bounds.
6. Configure a recoverer/DLT to store unprocessable records and investigation metadata.
7. Test retries, recovery, commits, and behavior when DLT publishing fails.
8. Monitor retry rates, DLT rates, consumer lag, and errors by exception type in production.

Do not classify mechanically by exception name alone. A single generic exception type can represent many causes; prefer specific business exceptions or controlled cause-chain analysis.

## 13. Common Misconceptions

1. **Thinking ExceptionClassifier performs retries itself.** The classifier only decides retryable vs. non-retryable; the error handler coordinates backoff and the recoverer.
2. **Thinking every exception should be retried.** Data or configuration errors do not resolve themselves on retry.
3. **Thinking non-retryable means the record is dropped immediately.** The error handler can still invoke a recoverer, such as publishing the record to a DLT.
4. **Confusing classification with retry count.** Attempt counts and wait durations are controlled by `BackOff`.
5. **Ignoring nested exceptions.** The listener container or libraries may wrap the root exception; configure the classifier appropriately for the cause chain.
6. **Assuming DefaultErrorHandler settings apply to retry topics.** `@RetryableTopic` has its own include/exclude mechanism.
7. **Assuming a standard error handler automatically controls transaction rollbacks.** Transactional containers use the configured after-rollback processor.
8. **Omitting ErrorHandlingDeserializer when expecting the container to handle deserialization errors.** Those errors occur before the listener and must be turned into error metadata for the error handler.
9. **Assuming DLT publishing always succeeds.** Observe the send result and confirm recovery only when the recoverer completes properly.

ExceptionClassifier enables Spring Kafka to apply error policies based on the nature of an exception. Keep classification, backoff, and recovery cleanly separated; apply bounded retries to transient errors, route unrecoverable errors to a DLT, and test offset commits as well. Proper classification keeps consumers from stalling on a bad record while avoiding discarding recoverable transient failures.
