# KafkaListenerErrorHandler

In a Spring Kafka application, an individual listener may need its own error-handling policy: recording the failing payload, adding business context to logs, storing audit trails for investigation, or deciding whether to escalate the error to the shared retry mechanism. `KafkaListenerErrorHandler` provides an extension point at the individual `@KafkaListener` level to carry out these tasks.

This interface belongs to the adapter layer that invokes the listener method. It receives the converted message along with the exception thrown by the listener. The handler can handle the error and return normally, or rethrow an exception so the container applies consumer-level error handling. Therefore, it is important to understand the difference between these two choices before configuring it.

## 1. Where KafkaListenerErrorHandler Sits in the Processing Flow

For a record listener, the high-level processing flow is as follows:

1. The consumer polls records from Kafka.
2. Spring Kafka converts the record into arguments matching the `@KafkaListener` method signature.
3. The adapter invokes the listener method.
4. If the listener throws an exception, the adapter invokes the `KafkaListenerErrorHandler` declared for that listener.
5. If the handler returns normally, the error is considered handled at the listener level. If the handler throws an exception, that exception propagates up to the container so `CommonErrorHandler` decides on retries, recovery, or forwarding to a dead-letter topic (DLT).

`KafkaListenerErrorHandler` does not replace the container error handler. It is suited for applying logic tied to a specific listener, whereas the container error handler manages record processing lifecycle, backoff, seeks, commits, and recovery.

## 2. Declaring a Bean and Attaching It to @KafkaListener

`KafkaListenerErrorHandler` is a functional interface. Its `handleError` method receives two arguments:

- `Message<?> message`: the converted Spring message containing payload and headers.
- `ListenerExecutionFailedException exception`: the exception representing the failure during listener invocation; the root cause is typically in `getCause()`.

The following example records business failure information and then rethrows the exception to the container:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.listener.KafkaListenerErrorHandler;

@Configuration
class ListenerErrorConfiguration {

    @Bean
    KafkaListenerErrorHandler orderListenerErrorHandler(
            FailureAuditService failureAuditService) {

        return (message, exception) -> {
            failureAuditService.recordFailure(
                    message.getPayload(), message.getHeaders(), exception);
            throw exception;
        };
    }
}
```

`FailureAuditService` is an application business service responsible for recording failure trails. Method names and data types of the service should be adapted to your actual model. If recording the audit fails, the exception from that operation must also be handled per your chosen policy; do not pretend the original error has been recovered.

Attach the bean using the `@Bean` method name in the `errorHandler` attribute:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {

    private final OrderService orderService;

    OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "${app.kafka.orders-topic}",
            errorHandler = "orderListenerErrorHandler")
    public void onOrder(OrderCreated event) {
        orderService.handle(event);
    }
}
```

The name in `errorHandler` must match the Spring bean name. If this attribute is omitted, the listener uses the container's error-handling mechanism as configured on the factory.

## 3. Two Ways a Handler Can Complete and Their Implications

The most important decision is whether the handler returns normally or throws an exception. These two behaviors lead to different outcomes.

### Record Context Then Escalate to the Container

```java
@Bean
KafkaListenerErrorHandler orderListenerErrorHandler(
        FailureAuditService failureAuditService) {
    return (message, exception) -> {
        failureAuditService.recordFailure(
                message.getPayload(), message.getHeaders(), exception);
        throw exception;
    };
}
```

The handler performs supplementary work and throws the exception. The container receives the error and applies `CommonErrorHandler`, such as waiting per BackOff, retrying the record, or invoking a recoverer after retries are exhausted. This is the right option when the application wants to keep centralized retry and recovery policies.

Because the same record can be redelivered, the audit operation may run multiple times. Use an event ID, topic-partition-offset, or stable business key to prevent duplicate writes. If auditing is mandatory, rethrow the exception only after the audit information has been durably persisted.

### Persist the Failure for Recovery Then Mark Handled

```java
@Bean
KafkaListenerErrorHandler archiveAndHandleError(
        FailureArchive failureArchive) {
    return (message, exception) -> {
        failureArchive.persist(message, exception);
        return null;
    };
}
```

When the handler returns normally, the adapter treats the exception as handled. The container does not receive that exception to retry via `CommonErrorHandler`. For listeners without a request/reply contract, the return value is typically unused; what matters is that the handler completed normally.

Choose this approach only if `persist` has completed storing the failure durably or performed an equivalent recovery action. If you merely log and return, the record may be acknowledged under the current `AckMode` and never retried, even though business processing failed. If sending a message to a DLT with `KafkaTemplate`, wait for the send result to succeed before returning; do not fire an asynchronous send and let the listener finish immediately.

| Handler Outcome | Subsequent Behavior | When to Use |
| --- | --- | --- |
| Throws exception | Container receives the error and applies the container-level error handler | Want retry, backoff, or recovery per shared policy |
| Returns normally | Error is treated as handled at the listener level; not retried by container handler | Error has been durably persisted or successfully recovered |

## 4. Combining with CommonErrorHandler

`CommonErrorHandler` operates at the listener container level and is configured on `ConcurrentKafkaListenerContainerFactory`. The example below sets a shared retry policy for listeners using this factory:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler commonKafkaErrorHandler() {
    // One initial processing attempt and up to two retries, spaced one second apart.
    return new DefaultErrorHandler(new FixedBackOff(1_000L, 2L));
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultErrorHandler commonKafkaErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(commonKafkaErrorHandler);
    return factory;
}
```

When the listener throws an exception, `KafkaListenerErrorHandler` can record an audit entry and rethrow for `DefaultErrorHandler` to handle. If the listener error handler returns normally, the container does not see that exception to perform retries. `FixedBackOff` in the example permits two retries after the first attempt; once retries are exhausted, configure a recoverer matching your data policy, such as `DeadLetterPublishingRecoverer` to emit records to a DLT.

Avoid creating two independent retry policies without defining their order and attempt counts. A listener-level handler should focus on local policy; the container-level handler should own consumer retries, seeks, commits, and recovery.

## 5. Data Observable Inside the Handler

The `Message<?>` object provides the converted payload and the headers populated by the message converter. This is a convenient place to extract data for logging or auditing, such as event type, business keys, and Kafka metadata if mapped into headers.

Do not assume the payload is always a specific DTO. The payload type depends on deserializer configuration, message converter, and the listener method signature. If the listener accepts `Message<OrderCreated>`, the payload is usually `OrderCreated`; if the listener accepts another type, the handler receives that corresponding payload type. Record both record-identifying metadata and the exception so you can trace back to topic, partition, offset, or event ID.

`ListenerExecutionFailedException` supplies listener error context. When classifying business errors, inspect the `cause` chain rather than relying solely on the message string. You can distinguish transient errors like dependent service timeouts from data errors that cannot be fixed by retrying, such as payloads violating business rules.

## 6. Variants with Consumer and Acknowledgment

Beyond `KafkaListenerErrorHandler`, Spring Kafka provides extended interfaces when additional context is needed:

- `ConsumerAwareListenerErrorHandler` additionally supplies the `Consumer<?, ?>` object.
- `ManualAckListenerErrorHandler` additionally supplies `Acknowledgment` when the listener uses manual acknowledgment mode.

Use these variants only when you genuinely need access to those objects. `Consumer` is not safe for concurrent use from multiple threads. In particular, never call `seek` yourself inside a listener error handler: the container does not track seeks performed at the adapter layer, and offset state can become inconsistent. If you need to control seeks or rewind read positions, implement that logic in `CommonErrorHandler` at the container level.

Similarly, do not call `acknowledge()` just to make an error disappear. With manual acknowledgment, acknowledging must follow completion of business logic and the container's `AckMode`. Acknowledging too early can cause a record to be skipped after the consumer restarts.

## 7. Errors Outside the Scope of Listener Error Handlers

`KafkaListenerErrorHandler` is invoked when the adapter handles an exception raised by calling the listener. It is not a catch-all for every error across the entire consumer lifecycle. Several scenarios require other mechanisms:

| Scenario | Mechanism to Consider |
| --- | --- |
| Listener throws exception while processing an event | `KafkaListenerErrorHandler` and/or `CommonErrorHandler` |
| Deserialization fails before a valid payload exists | `ErrorHandlingDeserializer` combined with container error handler |
| Need retry, seek, offset recovery, or DLT at consumer level | `CommonErrorHandler`, such as `DefaultErrorHandler` with a recoverer |
| Batch listener fails on a specific element | Batch error handling and `BatchListenerFailedException` |
| Errors involving transactions and rollbacks | Container transaction configuration with an appropriate after-rollback processor |

For deserialization errors, `ErrorHandlingDeserializer` can store exception details in headers so container-level handling can inspect them. Do not expect `KafkaListenerErrorHandler` to receive a valid business object when data failed to deserialize.

For a batch listener, a single invocation can contain many records and needs to pinpoint the exact failing record. Use container-level batch error handling; a listener error handler does not replace batch failure position metadata.

## 8. Designing a Safe Handler

An operationally sound handler generally follows these principles:

1. Distinguish transient errors from non-retryable errors via intentional exception classification.
2. If you want retries, record necessary context and rethrow the exception so the container decides.
3. If you want to mark the error handled, persist the failure or recovery outcome durably before returning normally.
4. Make auditing, failure persistence, and DLT publishing idempotent because they may execute multiple times.
5. Never commit offsets or seek manually inside a listener-level error handler.
6. Avoid logging entire payloads if they contain sensitive data; prefer event IDs and selected metadata.
7. Measure retry counts, recovered records, DLT transfers, and processing durations to detect prolonged failures.

## 9. Implementation and Testing Checklist

- [ ] The `KafkaListenerErrorHandler` bean is registered in the Spring context.
- [ ] The `errorHandler` attribute on `@KafkaListener` references the exact bean name.
- [ ] The handler clearly separates throwing exceptions from returning normally.
- [ ] If returning normally, the error has been durably stored or recovered.
- [ ] If throwing exceptions, `CommonErrorHandler`, BackOff, and the recoverer have a clear policy.
- [ ] Auditing and DLT publishing have deduplication mechanisms for redelivered records.
- [ ] No arbitrary offset commits or seeks occur inside the listener-level handler.
- [ ] Deserialization, batch, and transactional errors are handled at their proper layers.

When testing, create a listener that intentionally throws an exception and verify the handler is invoked with the expected payload, headers, and root cause. Test both branches separately: when the handler rethrows, the container retries according to BackOff; when the handler persists the failure and returns, the record is treated as handled according to `AckMode`. Also test the case where the audit service or failure store itself fails, ensuring the application never silently acknowledges an unrecovered record. Finally, verify DLT routing and duplicate-processing protection when the consumer receives the record again.
