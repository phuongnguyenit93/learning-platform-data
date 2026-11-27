# Consumer<ErrorMessage> and error-handler-definition

When a message enters a Spring Cloud Stream input binding and the handler function throws an exception, the framework needs to route the error to an appropriate handling mechanism. Under the functional model, an application can register a `Consumer<ErrorMessage>` bean to receive error details alongside the message that caused the failure. The `error-handler-definition` property links that bean to the target input binding.

This mechanism is useful when an application needs to record business errors, create audit entries, send alerts, or invoke a support service. However, a custom error handler is an application-level choice and replaces the default framework/binder error handlers for that binding. If you choose this approach, the binder's DLQ configuration will not automatically route failed messages to a DLQ. Understand the difference between application-level error handling and broker/binder-managed error handling before choosing.

## 1. What Information Does `ErrorMessage` Contain?

`org.springframework.messaging.support.ErrorMessage` is a Spring `Message` whose payload is of type `Throwable`. The payload is typically the exception thrown during processing. In many cases, that exception is a `MessagingException` and may contain the failed message.

An `ErrorMessage` can provide:

| Component | Meaning |
|---|---|
| `getPayload()` | The exception causing the failure, of type `Throwable` |
| `getHeaders()` | Headers of the `ErrorMessage`, which may contain diagnostic metadata |
| `getOriginalMessage()` | The original message at the point the `ErrorMessage` was created, if present |
| `MessagingException.getFailedMessage()` | The failed message retained by the exception, if the payload is a `MessagingException` and carries this data |

Do not assume `getOriginalMessage()` is always non-null. Some errors occur before the framework can attach the original message to the `ErrorMessage`. Check for null before reading the payload or headers of the original message.

Example:

~~~java
ErrorMessage errorMessage = ...;

Throwable failure = errorMessage.getPayload();
Message<?> original = errorMessage.getOriginalMessage();

if (original != null) {
    Object messageId = original.getHeaders().getId();
    Object payload = original.getPayload();
}
~~~

`ErrorMessage` is not the original business payload. Its payload is the exception. To read order data, event ID, or correlation headers, retrieve them from the original message or the failed message inside the exception.

## 2. Error Path in an Input Binding

For an imperative `Function` or `Consumer`, when the message handler throws an exception, the error is propagated back to the binder. The binder/framework retry mechanism may retry the message before handing the error over to the final handling mechanism. After attempts fail, the framework may:

- Log the error.
- Route the error to the application's custom error handler.
- Use the binder's own mechanism to requeue or send the message to a Dead Letter Queue (DLQ), if configured and supported by the broker.

~~~mermaid
flowchart TD
    A["Broker sends message"] --> B["Input binding"]
    B --> C["Function / Consumer"]
    C -->|Success| D["Processing complete"]
    C -->|Throws exception| E["Retry per configuration"]
    E -->|Attempts left| C
    E -->|Attempts exhausted| F{"Error handling mechanism"}
    F --> G["Consumer<ErrorMessage>"]
    F --> H["Binder handler / DLQ"]
    F --> I["Log and default handling"]
~~~

Attempt counts and final behavior depend on the programming model, binder, and configuration. Current Spring Cloud Stream documentation describes a default of three retry attempts for imperative message handlers; afterward, the binder decides whether to drop, requeue, or DLQ based on its capabilities and settings.

Do not apply this diagram mechanically to reactive functions. Reactive functions wire `Publisher`s together rather than processing individual messages like imperative handlers. Errors inside a Reactor pipeline must be handled using operators such as `onErrorResume` or `retryWhen`.

## 3. Creating `Consumer<ErrorMessage>` as a Custom Error Handler

A custom error handler is a functional bean of type `Consumer<ErrorMessage>`. The bean is registered in the Spring Function Catalog, though it does not automatically become the handler for every binding. Specify the bean name explicitly via `error-handler-definition`.

The example below logs error details and metadata from the original message. Persistence is placed behind an interface so it can be backed by a database, audit system, or alerting service:

~~~java
import java.time.Instant;
import java.util.function.Consumer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

record FailureRecord(
    String bindingName,
    String messageId,
    String exceptionType,
    String exceptionMessage,
    Instant occurredAt
) {}

@FunctionalInterface
interface FailureRecorder {
    void record(FailureRecord record);
}

@Configuration
class OrderErrorConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(OrderErrorConfiguration.class);

    @Bean
    Consumer<ErrorMessage> orderErrorHandler(FailureRecorder recorder) {
        return error -> {
            Throwable failure = error.getPayload();
            Message<?> original = error.getOriginalMessage();

            String messageId = original == null
                ? "unknown"
                : String.valueOf(original.getHeaders().getId());

            String payloadType = original == null
                ? "unknown"
                : original.getPayload().getClass().getSimpleName();

            log.error(
                "Order processing failed: messageId={}, payloadType={}",
                messageId,
                payloadType,
                failure
            );

            recorder.record(new FailureRecord(
                "processOrder-in-0",
                messageId,
                failure.getClass().getName(),
                failure.getMessage(),
                Instant.now()
            ));
        };
    }
}
~~~

In the example:

- `orderErrorHandler` is the bean name referenced from configuration.
- `getPayload()` extracts the exception to log the error type and stack trace.
- `getOriginalMessage()` retrieves the original message if supplied by the framework.
- `FailureRecorder` separates recording from reading `ErrorMessage`.
- The handler logs only necessary metadata; do not log the full payload because the message may contain personal data, payment details, or business secrets.

An `ErrorMessage` may lack an original message. The handler should cope with this case instead of throwing a secondary `NullPointerException`. Also design `FailureRecorder` with appropriate timeouts and resilience; if audit recording itself fails, do not let the secondary error obscure the original exception.

## 4. Attaching a Handler to an Input Binding via `error-handler-definition`

Suppose the application has a `Function` named `processOrder`; its default input binding is `processOrder-in-0`. Configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
          error-handler-definition: orderErrorHandler
~~~

Property to note:

~~~text
spring.cloud.stream.bindings.processOrder-in-0.error-handler-definition
~~~

The value `orderErrorHandler` must match the registered `Consumer<ErrorMessage>` bean name. The property sits directly under the binding, at the same level as `destination`, `group`, and `consumer`; do not place it inside `consumer`.

`error-handler-definition` associates the error handler with the input binding. It is not a destination name, consumer group name, or business bean name. The `processOrder` bean continues processing messages normally; the `orderErrorHandler` bean only receives `ErrorMessage` when the binding fails under the corresponding mechanism.

Explicitly declare `spring.cloud.function.definition` to identify the business functions to activate. The error handler also lives in the Function Catalog; if the application contains multiple function beans, declaring `definition` explicitly prevents unintended function auto-discovery.

## 5. Using a Default Error Handler for Multiple Functions

If multiple input bindings require the same error-recording behavior, you can configure a default handler:

~~~yaml
spring:
  cloud:
    function:
      definition: "processOrder;processShipment"
    stream:
      default:
        error-handler-definition: commonErrorHandler
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
        processShipment-in-0:
          destination: shipments.submitted
          group: shipment-service
~~~

The `commonErrorHandler` bean is a `Consumer<ErrorMessage>` used as the default handler for function bindings. This configuration works well when audit, alerting, and error persistence policies are uniform.

If one binding needs dedicated information or handling, declare `error-handler-definition` directly on that binding. For example:

~~~yaml
spring:
  cloud:
    function:
      definition: "processOrder;processShipment"
    stream:
      default:
        error-handler-definition: commonErrorHandler
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
          error-handler-definition: orderErrorHandler
        processShipment-in-0:
          destination: shipments.submitted
          group: shipment-service
~~~

Here `processOrder-in-0` uses its dedicated `orderErrorHandler`; `processShipment-in-0` uses the default `commonErrorHandler`. Name beans and bindings clearly so multiple streams remain easy to trace.

## 6. Explicit Binding Name Mapping

If an application renames the default binding using `spring.cloud.stream.function.bindings`, the `error-handler-definition` property must use the mapped binding name.

Example:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
      bindings:
        processOrder-in-0: ordersInput
    stream:
      bindings:
        ordersInput:
          destination: orders.submitted
          group: order-service
          error-handler-definition: orderErrorHandler
~~~

After mapping, `ordersInput` is the binding name used in Stream configuration. Thus, the handler is configured at:

~~~text
spring.cloud.stream.bindings.ordersInput.error-handler-definition
~~~

If you map the input to `ordersInput` but still place the handler under `processOrder-in-0`, the configuration may not apply to the actual binding. When troubleshooting, verify the mapped binding name before checking the handler bean name.

## 7. Distinguishing Custom Error Handler from Retry and DLQ

The three mechanisms have distinct responsibilities:

| Mechanism | Responsibility | Configuration Example |
|---|---|---|
| Retry | Re-attempt message processing when errors may be transient | `consumer.max-attempts`, backoff |
| Custom error handler | Receive `ErrorMessage` to audit, notify, or execute application handling | `error-handler-definition` |
| Binder DLQ | Route failed messages to a broker error destination for inspection or replay | `enable-dlq`, `auto-bind-dlq` |

Spring Cloud Stream's custom error handler disables the default error handlers supplied by the framework/binder so they do not interfere with one another. When a custom `Consumer<ErrorMessage>` is attached, the binder-specific DLQ mechanism will not send failed messages to the DLQ, even if DLQ configuration remains enabled.

This is an important design consideration:

- Choose `Consumer<ErrorMessage>` when the application needs to handle error details itself, such as writing audits or sending alerts.
- Choose the binder's DLQ when you need the broker to retain failed messages for operations teams to inspect or replay.
- If you need both auditing and a DLQ, you can use the broker's DLQ and deploy a separate consumer reading from the DLQ to record audits. This keeps message retention responsibility on the broker.

Do not enable a custom error handler while expecting the binder to automatically DLQ the same message. If the handler manually forwards the message to another destination, that is application-implemented logic; you must manage send failures, deduplication, and error-forwarding loops yourself.

## 8. Configuring Retry Before Forwarding Errors

For imperative message handlers, you can configure attempt counts and wait intervals on the input binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
          consumer:
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
          error-handler-definition: orderErrorHandler
~~~

`max-attempts` is the total number of processing attempts under the retry configuration. The backoff properties control the progressively increasing pause between attempts. Defaults are typically three attempts, a one-second initial wait, a ten-second maximum, and a multiplier of two; verify against your project's Spring Cloud Stream and binder versions.

Retry fits transient errors such as dependent-service timeouts or intermittent connectivity. Do not retry indefinitely for schema-invalid data or business-rule violations because subsequent attempts normally cannot fix bad data.

Once retries are exhausted, the custom error handler can record the `ErrorMessage`. The handler does not automatically trigger another retry of the message. If reprocessing is desired, you need an explicit policy such as a DLQ, outbox, controlled replay, or a new business command.

## 9. When to Use Kafka or RabbitMQ DLQ?

If the goal is to retain failed messages on the broker, use the binder-supported DLQ feature rather than a custom `Consumer<ErrorMessage>`.

### 9.1. Kafka Binder

The Kafka binder requires an explicit consumer group to enable DLQ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
          consumer:
            max-attempts: 3
    kafka:
      bindings:
        processOrder-in-0:
          consumer:
            enable-dlq: true
~~~

After attempts fail, the binder sends the record to the DLQ per configuration. The default name typically follows `error.<destination>.<group>`; it can be customized via Kafka binder DLQ properties. Verify the DLQ partition count because the Kafka binder by default may publish the record to the same partition number as the original record.

### 9.2. RabbitMQ Binder

The RabbitMQ binder can automatically create a dead-letter queue for a consumer binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
          consumer:
            max-attempts: 3
    rabbit:
      bindings:
        processOrder-in-0:
          consumer:
            auto-bind-dlq: true
~~~

The Rabbit binder creates the DLQ queue wired into the corresponding topology. Properties such as `requeue`, `republish-to-dlq`, and dead-letter exchange have specific semantics; consult the documentation for your exact Rabbit binder version.

Do not copy Kafka DLQ settings to RabbitMQ or vice versa. With Pulsar, check the dead-letter policy and capabilities of the Pulsar binder / Spring for Apache Pulsar version in use.

## 10. Scope of `error-handler-definition`

`error-handler-definition` binds a custom error consumer to input binding errors under the message-handler model. Do not treat it as a catch-all handler for every error in the application.

| Error Type | Mechanism to Inspect |
|---|---|
| Imperative `Function` throws exception while processing a message | Retry and error handler bound to the input binding |
| Imperative `Consumer` throws exception | Retry and error handler bound to the input binding |
| Errors inside a reactive `Function<Flux<T>, Flux<R>>` | Reactor operators such as `onErrorResume`, `retryWhen`; does not directly apply imperative `RetryTemplate` mechanics |
| Message send errors on an output binding | Error channel / producer error handling and binder features |
| Deserialization errors before the message handler receives a payload | Binder-specific deserialization error handler, e.g., Kafka or Kafka Streams |
| Errors initializing broker connections or binding configuration | Startup logs, binder health, connection retries, and operational settings |

If an error occurs before the framework constructs a message for the input handler, do not assume the binding's custom `Consumer<ErrorMessage>` will receive it. For instance, a Kafka deserialization exception may be handled by the Kafka binder's or Kafka Streams binder's dedicated deserialization exception handler.

Similarly, errors raised when sending a message from an output binding are not input-binding processing errors. Use the corresponding error channel or producer error-handling mechanism.

## 11. Writing Safe and Operable Handlers

A custom error handler runs on the error-handling path. If the handler itself throws an exception, handling of the original failure can become unpredictable. Design the handler as an operational component with clear boundaries:

- Check that `ErrorMessage.getOriginalMessage()` can be null.
- Extract the exception from `getPayload()` and preserve the root cause when logging.
- Record message ID, binding, exception type, and timestamp; store payload only when permitted by an appropriate data policy.
- Do not log tokens, passwords, payment details, or full sensitive payloads.
- Set timeouts on HTTP calls or external audit operations.
- Use an idempotency key when writing error records to avoid duplication on redelivery.
- Distinguish transient errors from unrecoverable data errors.
- Alert on rising error rates rather than sending an operational notification for every failed message under high traffic.
- Monitor errors thrown by the error handler itself so they do not disappear in general logs.

A handler should perform a small set of tasks that complete quickly and reliably. If lengthy investigation work is required, persist error metadata and offload the work to a separate queue or processing system.

## 12. Testing `Consumer<ErrorMessage>`

Test the error handler's logic separately from how the framework wires the handler to the binding.

### 12.1. Direct Unit Testing of the Consumer

You can construct an `ErrorMessage` in memory to verify the handler reads both the exception and the original message:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

class OrderErrorHandlerTest {

    @Test
    void recordsExceptionAndOriginalMessageId() {
        List<FailureRecord> records = new ArrayList<>();
        FailureRecorder recorder = records::add;
        var configuration = new OrderErrorConfiguration();
        var handler = configuration.orderErrorHandler(recorder);

        Message<String> original = MessageBuilder
            .withPayload("order-900")
            .build();
        ErrorMessage error = new ErrorMessage(
            new IllegalStateException("inventory unavailable"),
            original
        );

        handler.accept(error);

        assertEquals(1, records.size());
        assertEquals(
            original.getHeaders().getId().toString(),
            records.get(0).messageId()
        );
        assertEquals(
            IllegalStateException.class.getName(),
            records.get(0).exceptionType()
        );
    }
}
~~~

This test verifies `ErrorMessage` handling logic without a broker. You can add cases where `originalMessage` is null and where `FailureRecorder` throws an exception.

### 12.2. Integration Testing with the Test Binder

To verify wiring, create an input function that intentionally throws an exception for a given payload, configure `error-handler-definition`, send a message to the Test Binder's input destination, and verify the recorder receives the corresponding `ErrorMessage`.

Integration tests should verify:

1. The bean name in `error-handler-definition` is found in the Function Catalog.
2. The right binding is targeted and the handler is not registered as a regular input function.
3. The `ErrorMessage` contains the expected exception.
4. The original message and message ID are preserved if provided by the binder/framework.
5. Either the default handler or per-binding handler is invoked per configuration.
6. When using a DLQ, a separate test verifies the binder-native mechanism without simultaneously configuring a custom handler.

The Test Binder is useful for verifying in-application message routing, but it does not replace integration tests against a real broker for acknowledgment, retry, requeue, and DLQ.

## 13. Procedure for Choosing and Configuring an Error Handler

When a binding requires error handling, proceed in order:

1. Identify whether the failure occurs in an imperative handler, reactive pipeline, deserialization, or producer.
2. Identify the input binding and the binding name after any mapping.
3. Decide whether the application needs a custom error consumer or wants the binder to manage retry/requeue/DLQ.
4. If choosing a custom handler, create a `Consumer<ErrorMessage>` bean with explicit null and dependency-failure handling.
5. Declare `spring.cloud.function.definition` for business functions.
6. Place `error-handler-definition` directly under the binding or configure `spring.cloud.stream.default.error-handler-definition` if shared.
7. Configure retry for transient errors if needed and verify post-final-attempt behavior.
8. Do not expect binder DLQ to operate automatically while a custom error handler is attached.
9. Write unit tests for the `Consumer` and integration tests for wiring.
10. Observe logs, metrics, audit records, and backlog to confirm errors follow policy.

## 14. Common Configuration Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Handler is not called | Wrong bean name in `error-handler-definition` | Match bean name with configuration |
| Handler attached to wrong binding | Used old binding name after mapping | Use the alias under `spring.cloud.stream.function.bindings` |
| App reports unable to determine function | Multiple function beans present without `spring.cloud.function.definition` | Explicitly declare business functions |
| No DLQ messages despite DLQ enabled | Custom error handler replaces the binder error handler | Pick one mechanism: custom handler or binder DLQ |
| Handler throws `NullPointerException` | Assumed original message is always present | Check for null before reading the message |
| Errors persist after writing audit | Handler does not fix the root cause or downstream call still fails | Distinguish auditing from retry/requeue and check binder |
| Deserialization errors never reach handler | Error occurs before the message handler | Use the binder's dedicated deserialization error handler |
| Producer errors do not enter handler | `error-handler-definition` is attached to an input binding | Check producer error channel and binder-specific handler |

## Official References

- [Spring Cloud Stream - Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html): `Consumer<ErrorMessage>`, `error-handler-definition`, default handlers, retry, and DLQ.
- [Spring Framework - ErrorMessage Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ErrorMessage.html): `Throwable` payload and `getOriginalMessage()`.
- [Spring Cloud Stream - Kafka Dead-Letter Topic Processing](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/dlq.html): group requirements, retry, and enabling DLQ for the Kafka binder.
- [Spring Cloud Stream - Kafka Binder Reference](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-kafka.html): DLQ properties and Kafka consumer-specific settings.
