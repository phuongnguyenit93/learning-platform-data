# Classifying Conversion Errors, Business Errors, and Infrastructure Errors

An unprocessable message can stem from several causes: the payload cannot be converted to a Java type, the data violates business rules, or a dependency such as a database, API, or broker is temporarily unavailable. These three error categories require different responses. Retrying a schema-invalid payload will only repeat the failure; ignoring a database timeout can cause event loss; and routing a valid business decision such as "order rejected" to a DLQ distorts the meaning of the workflow.

In Spring Cloud Stream, classification starts from where the error originates and whether the cause is recoverable. Identify whether the failure occurred during message conversion, inside business rules, or when communicating with infrastructure; then decide whether to retry, reject at the business level, quarantine the data, or route the message to a DLQ.

## 1. The Three Error Categories and How to Identify Them

| Error Category | Typical Causes | Self-Recoverable? | Default Handling Direction |
|---|---|---|---|
| Conversion | Malformed JSON, type mismatch, incompatible schema, missing required field at deserialization layer | Usually not, if a fixed payload is invalid | Do not retry repeatedly; quarantine/DLQ and investigate contract |
| Business | Order does not meet conditions, disallowed state, credit limit exceeded, invalid customer | Does not self-recover merely by retrying | Return rejection result or emit corresponding business event |
| Infrastructure | Timeout, connection loss, overloaded broker/API/database, HTTP 5xx, or throttling | Often yes, depending on the error | Bounded retry, backoff, circuit breaker; then recovery/DLQ |

Do not classify solely by exception name. The same generic exception such as `IllegalStateException` can be thrown by a programming bug, business data, or dependency state. Create dedicated semantic exceptions and preserve the root cause so logs, metrics, and retry policies can make the right decision.

### A Simple Decision Tree

~~~text
Unprocessable message
          |
          v
Can the payload be read/decoded?
    | No
    +------> Conversion error
    |          -> inspect content-type/schema
    |          -> quarantine/DLQ, avoid futile retries
    |
    | Yes
    v
Does the data violate business rules?
    | Yes
    +------> Business error
    |          -> rejection result / rejected event
    |          -> do not retry like an infrastructure error
    |
    | No
    v
Is a dependency or broker experiencing a temporary error?
    | Yes
    +------> Infrastructure error
    |          -> bounded retry with backoff
    |          -> DLQ/alert if attempts are exhausted
    |
    | No
    +------> Programming bug or unclassified error
               -> record, investigate, and handle explicitly
~~~

## 2. Conversion Errors: Message Type Mismatch

Spring Cloud Stream receives a message from the binder and uses a message converter to transform the payload into the type declared by the function or consumer. Errors can occur before the function is invoked, for example:

- The producer sends invalid JSON or a truncated payload.
- The `content-type` header declares the wrong format.
- A JSON field has a different type from the DTO, such as a string sent into a numeric field.
- Producer and consumer schemas are incompatible.
- The consumer requires a mandatory field that an older message lacks.
- The deserializer cannot read the payload bytes or the schema ID does not exist.

Example consumer declaring a DTO:

~~~java
import java.math.BigDecimal;

public record OrderCreated(
    String orderId,
    String customerId,
    BigDecimal total
) {}
~~~

Matching message:

~~~json
{
  "orderId": "ord-1001",
  "customerId": "cus-2001",
  "total": 125000.00
}
~~~

Type-mismatch error message:

~~~json
{
  "orderId": "ord-1001",
  "customerId": "cus-2001",
  "total": "one hundred"
}
~~~

If the converter cannot convert `total` into `BigDecimal`, the function may never be invoked. Therefore, placing a `try/catch` inside the function will not catch all conversion errors. You must inspect binding error logs/error handling and converter/schema configuration at the message-receiving boundary.

### Distinguishing Conversion Errors from Validation

A payload can convert into a DTO successfully and still be invalid from a business perspective. For example, `total = -100` is a valid number for `BigDecimal`, but invalid under order rules. This case belongs to validation/business logic, not deserialization failure.

Conversely, `total = "abc"` cannot be converted into a number and is a conversion error. This distinction matters because conversion errors are typically handled before the business handler runs, whereas business errors require a meaningful response for the workflow.

### How to Handle Conversion Errors

1. Inspect the raw payload and `content-type` header from the producer.
2. Cross-check the schema or DTO contract on both sides.
3. Determine whether the error comes from an older message that was valid under a previous schema version.
4. Quarantine the failing message, retaining source info, offset/message ID, and error reason.
5. Fix the producer, converter, or schema, then perform controlled replay.

Do not infinitely retry a syntactically invalid JSON payload. If the same payload bytes are redelivered, conversion will usually fail again. Retry only makes sense when a conversion error actually stems from a temporary dependency issue, such as a temporarily unreachable schema registry; in that case, the root cause is an infrastructure error during schema lookup, not a bad payload.

## 3. Business Errors: Structurally Valid Data That Is Not Accepted

A business error occurs when the application understands the message, but business rules do not allow the action to proceed. For example:

- An order has a zero or negative total.
- The order status does not allow confirmation.
- The credit limit has been exceeded.
- Inventory has insufficient stock to accept the request.
- The customer ID does not exist in the business domain.

Not every unsuccessful business outcome is an exception. If rejection is an expected outcome of the workflow, it can be represented with an explicit result type or by emitting an event such as `OrderRejected`. Use exceptions for abnormal failures or to integrate with error handling when needed, but do not turn every business decision into a technical error.

Example distinguishing outcomes:

~~~java
public sealed interface OrderDecision
    permits OrderAccepted, OrderRejected {}

public record OrderAccepted(String orderId)
    implements OrderDecision {}

public record OrderRejected(
    String orderId,
    String reasonCode
) implements OrderDecision {}
~~~

The function can return one of the two outcomes:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderDecisionFunctions {

    @Bean
    Function<OrderCommand, OrderDecision> decideOrder() {
        return command -> {
            if (command.total().signum() <= 0) {
                return new OrderRejected(
                    command.orderId(),
                    "TOTAL_MUST_BE_POSITIVE"
                );
            }

            return new OrderAccepted(command.orderId());
        };
    }

    public record OrderCommand(
        String orderId,
        java.math.BigDecimal total
    ) {}
}
~~~

Place `OrderDecision`, `OrderAccepted`, `OrderRejected`, and `OrderDecisionFunctions` in separate Java files in the same package (each top-level `public` type in a file of the same name). In the example, `OrderCommand` is a nested record inside `OrderDecisionFunctions`.

A rejection result is still a normal processing outcome. You can route `OrderAccepted` and `OrderRejected` to corresponding outputs or consumers via application logic. Do not retry a request with a negative total if the data has not changed; retrying will only repeat the same decision.

### When to Use Exceptions for Business Errors?

Some business errors need to halt the handler and be routed to a separate handling flow, for example when reference data does not yet exist due to out-of-order events. Distinguish between:

- **Final rejection:** rules cannot change by retrying; return a rejected outcome.
- **Not yet decidable:** dependent data has not arrived yet or state is still being updated; bounded retry, delay, or routing to a waiting flow may be appropriate.
- **Contract violation:** the producer sent an impossible state; record and quarantine for investigation.

Do not label all of the cases above as "business exception" and apply the same policy to them. Reason codes and recoverability must be expressed explicitly.

## 4. Infrastructure Errors: Dependencies Temporarily Unavailable

Infrastructure errors typically occur when a function has received a valid payload but cannot complete the operation due to a dependency:

- Database timeout, connection pool exhaustion, or failover.
- Partner API returning HTTP 429, 502, 503, or 504.
- DNS, TLS, or network connectivity failures.
- Broker temporarily unavailable or refusing publish.
- Schema registry service unreachable.
- Storage system overloaded.

Example service saving an order:

~~~java
public class OrderPersistenceService {

    private final OrderRepository repository;

    public OrderPersistenceService(OrderRepository repository) {
        this.repository = repository;
    }

    public void save(OrderCreated event) {
        try {
            repository.save(toEntity(event));
        } catch (org.springframework.dao.TransientDataAccessException ex) {
            throw new TransientDependencyException(
                "Temporary database failure while saving order",
                ex
            );
        }
    }

    private OrderEntity toEntity(OrderCreated event) {
        return new OrderEntity(event.orderId(), event.total());
    }
}
~~~

Only wrap failures identified as transient. Do not turn every `DataAccessException` into a retryable error: constraint violations, invalid SQL, or invalid data can be permanent errors. Classify based on the specific driver/framework exception and root cause.

For HTTP, timeouts or 5xx responses are usually retryable; 429 should honor `Retry-After` if present; 400 due to an invalid payload should generally not be retried; 401/403 usually require fixing credentials or permissions. Each API can have its own semantics, so check the dependency's contract.

## 5. Defining Exceptions by Recoverability

A clear exception convention makes retry policies easy to read:

~~~java
public class InvalidEventException extends RuntimeException {
    public InvalidEventException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class BusinessRuleViolationException extends RuntimeException {
    public BusinessRuleViolationException(String message) {
        super(message);
    }
}

public class TransientDependencyException extends RuntimeException {
    public TransientDependencyException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class PermanentDependencyException extends RuntimeException {
    public PermanentDependencyException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Place each `public` exception in its own separate Java file in the same package. Consistently use `TransientDependencyException` for recoverable dependency failures; this class name is also referenced in the retry configuration in the next section.

Exception names should describe the cause and recoverability, not just the technical layer. For example, `TransientDependencyException` indicates it can be retried; `InvalidEventException` indicates the payload needs fixing or quarantine; `BusinessRuleViolationException` indicates a business rule rejected it.

Preserve the cause for logging and investigation. Do not merely throw `new RuntimeException("failed")`, as that loses the original HTTP status, SQL state, converter, or broker exception details.

## 6. Configuring Retry by Error Type in Spring Cloud Stream

Spring Cloud Stream supports retry for consumer bindings. You can limit the number of attempts and configure backoff:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            max-attempts: 4
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
            default-retryable: false
            retryable-exceptions:
              com.example.TransientDependencyException: true
              com.example.InvalidEventException: false
              com.example.BusinessRuleViolationException: false
              com.example.PermanentDependencyException: false
~~~

Meaning:

- `max-attempts: 4` is the maximum total number of processing attempts, including the initial attempt.
- `back-off-initial-interval` is the initial wait interval.
- `back-off-max-interval` caps the wait time between attempts.
- `back-off-multiplier` adjusts the growth rate of the wait time.
- `default-retryable: false` requires retrying only explicitly declared exceptions.
- `retryable-exceptions` maps exception class names to retry decisions.

This configuration is an example for a consumer binding using Spring Cloud Stream's retry mechanism. Verify properties and semantics according to the Spring Cloud Stream/binder version in use. With reactive functions, retries may need to be placed in the Reactor pipeline and the binding's retry boundary may differ; do not assume imperative retry configuration covers all reactive errors.

### Choosing Backoff and Limits

Retrying too fast can create a retry storm: many consumers simultaneously calling an overloaded dependency again, making recovery even harder. Exponential backoff and jitter help spread out retry timing. If the dependency returns `Retry-After`, consider honoring that guidance.

Set total retry duration to fit business timeouts and how long a message can wait. After the maximum attempts, a clear action is needed: DLQ, quarantine, alert, or manual remediation workflow. Do not retry infinitely on a consumer thread because it can hold the partition/queue and block other messages.

## 7. Errors at Producer, Function, and Consumer Have Different Paths

A Spring Cloud Stream application can encounter errors at multiple boundaries:

| Location | Example | What to Observe |
|---|---|---|
| Producer payload creation | Mapping or validation failure | Application logs, event creation metrics |
| Producer binding send | Broker rejects or fails publish | Send/confirm result, binder error |
| Consumer conversion | Unreadable JSON/schema | Converter/deserializer, error channel/binder log |
| Function processing | Business handler or dependency throws exception | Retry policy, error handling |
| Consumer commit/ack | Instance stops before acknowledgment | Redelivery, offset, duplicates |
| Consumer output emission | Target broker unavailable | Output binding producer error |

Do not use a single error handler to mask all errors. Event creation errors may require business rollback or outbox; publish errors require retaining the event for resending; deserialization errors require payload quarantine; business errors require a rejected outcome; temporary database errors require retry.

In particular, `StreamBridge.send(...)` returns a result for sending into the binding/channel according to the API and binder semantics. That return value should not be treated as universal proof that the message has been durably stored by the broker and processed by consumers. If publish confirmation is required, use the appropriate producer confirmation/acknowledgment mechanism of the binder and test the failure window.

## 8. Error Channels and Error Handling at the Spring Layer

Spring Integration and Spring Cloud Stream provide an error message mechanism so errors occurring during processing can be observed or handled on an error channel. An error message typically carries the exception as its payload and headers referencing the original message, if available.

A handler can log the error and forward necessary details to observability systems:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.stereotype.Component;

@Component
public class StreamErrorLogger {

    @ServiceActivator(inputChannel = "errorChannel")
    public void handle(Message<?> errorMessage) {
        Object payload = errorMessage.getPayload();

        if (payload instanceof MessagingException exception) {
            Throwable cause = exception.getCause();

            // Log the cause, original message, and binding context.
            // Do not log the entire payload if it contains sensitive data.
        }
    }
}
~~~

The example above illustrates receiving error messages on the global Spring Integration error channel. It does not replace retry, DLQ, or binder-specific error handling. Some errors occur before a message enters a function, and producer errors and reactive errors have different handling paths. Identify the actual error channel of the binding based on your configuration and version before implementing a handler.

Do not swallow the exception after logging if the message has not been processed or durably stored. If the handler returns normally without a recovery action, the framework may treat the error as handled while the event is lost from the intended processing flow.

## 9. DLQ and Quarantine for Unprocessable Messages

A Dead Letter Queue/Topic holds messages that have exhausted retries or cannot be processed under policy. Quarantine can be used for payloads violating contracts or data requiring investigation. They share similar goals but are not identical:

- A DLQ is typically a mechanism tied to the broker/binder and consumer failures.
- Quarantine is an application-workflow storage area for failed data, potentially retaining both the raw payload and diagnostics.
- A rejected event is a business outcome; it is not necessarily an error message.

With the Kafka binder, DLQ requires an explicit consumer group and dedicated configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor

      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
~~~

With the RabbitMQ binder, automatic DLQ binding can be enabled:

~~~yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
~~~

Property names, routing keys, queue/topic creation permissions, and dead-letter policies depend on the binder version. With Pulsar, configure the dead-letter policy via extended consumer properties and Pulsar subscription semantics; do not copy Kafka/RabbitMQ properties to Pulsar.

Messages in the DLQ must retain sufficient metadata for investigation: event ID, original source/destination, group/subscription, timestamp, delivery attempt count, exception class, and cause. Do not write secrets or entire sensitive payloads into error logs.

### DLQ Handling Workflow

1. Count and alert when the DLQ receives new messages or the oldest message age exceeds a threshold.
2. Classify the error: conversion, business, or infrastructure.
3. Identify the root cause and scope of impact.
4. Fix the schema, data, code, or dependency.
5. Choose to replay, repair data then replay, emit a compensating event, or retain if unprocessable.
6. Replay with a stable event ID and an idempotent consumer.
7. Verify that the DLQ backlog decreases and events are processed successfully.

Do not continuously auto-replay the entire DLQ. If the root cause has not been fixed, replaying only generates more errors and can cause overload.

## 10. Reactive Functions: Classifying Errors Inside the Pipeline

With reactive functions, errors can occur inside an operator or an inner publisher. Distinguish an item-level error from an error that terminates the entire publisher.

Example calling a reference service:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Configuration
public class ReactiveOrderFunctions {

    @Bean
    Function<Flux<OrderCreated>, Flux<OrderDecision>> processOrders(
            CustomerClient client) {

        return orders -> orders.flatMap(order ->
            client.findCustomer(order.customerId())
                .map(customer -> validate(order, customer))
                .switchIfEmpty(Mono.just(
                    new OrderRejected(
                        order.orderId(),
                        "CUSTOMER_NOT_FOUND"
                    )
                ))
                .onErrorMap(
                    TimeoutException.class,
                    ex -> new TransientDependencyException(
                        "Customer lookup timed out",
                        ex
                    )
                )
        );
    }

    private OrderDecision validate(
            OrderCreated order,
            Customer customer) {
        if (order.total().signum() <= 0) {
            return new OrderRejected(
                order.orderId(),
                "INVALID_TOTAL"
            );
        }
        return new OrderAccepted(order.orderId());
    }

    public interface CustomerClient {
        Mono<Customer> findCustomer(String customerId);
    }

    public record OrderCreated(
        String orderId,
        String customerId,
        java.math.BigDecimal total
    ) {}

    public record Customer(String customerId) {}

    public sealed interface OrderDecision
        permits OrderAccepted, OrderRejected {}

    public record OrderAccepted(String orderId)
        implements OrderDecision {}

    public record OrderRejected(String orderId, String reason)
        implements OrderDecision {}
}
~~~

The example uses `flatMap` so each event has its own inner publisher. Customer not found is a business outcome represented by `OrderRejected`; timeouts are mapped to a transient exception. In real code, import `java.util.concurrent.TimeoutException` if the client uses that exception, or map the HTTP client's specific exception.

`retryWhen` can be used for transient dependency calls:

~~~java
return client.findCustomer(order.customerId())
    .retryWhen(
        reactor.util.retry.Retry.backoff(3, Duration.ofMillis(200))
            .filter(this::isTransient)
    );
~~~

Place the retry around the inner publisher of the operation that needs retrying, rather than retrying the entire `Flux` if you do not want to reprocess previously completed events. If a publisher is resubscribed, side effects inside it may run again; only retry idempotent operations or use an idempotency key.

Do not convert all errors into `Mono.empty()`. Doing so can turn timeouts or serialization errors into "data not found," masking incidents and producing incorrect business outcomes.

## 11. Testing Each Error Category

Tests should prove that errors are classified and handled properly, not merely that an exception is thrown.

| Scenario | Error Category | Expected Result to Verify |
|---|---|---|
| Malformed JSON | Conversion | Function is not invoked; message is observed/quarantined by binder |
| `total` field is an unconvertible string | Conversion | No futile retries; contract diagnostics saved |
| Negative `total` | Business | Returns rejected or handled per business policy |
| Customer does not exist | Business | Rejection outcome or wait per explicit rule |
| Database timeout | Infrastructure | Bounded retry, backoff, and eventual recovery/DLQ |
| API returns 429 | Infrastructure/throttling | Honors Retry-After or throttles down |
| Invalid credentials | Infrastructure/configuration | No tight retry loop; operational alert |
| Broker disconnects during publish | Infrastructure | Publish failure observed; event can be re-emitted |
| Consumer stops before ack/commit | Delivery | Redelivery does not duplicate side effects thanks to idempotency |

Unit test for a business rule:

~~~java
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class OrderDecisionFunctionsTest {

    @Test
    void rejectsNonPositiveTotal() {
        OrderDecisionFunctions functions =
            new OrderDecisionFunctions();

        OrderDecision result = functions.decideOrder().apply(
            new OrderDecisionFunctions.OrderCommand(
                "ord-1001",
                new BigDecimal("-1")
            )
        );

        assertInstanceOf(OrderRejected.class, result);
    }
}
~~~

The test binder helps verify functions, bindings, and error flows within the application without a real broker. However, dedicated integration tests with Kafka, RabbitMQ, or Pulsar are needed to confirm retry, acknowledgment, DLQ, redelivery, and serialization under the actual binder.

For conversion errors, send a raw schema-invalid payload through a real broker or the corresponding test adapter. A unit test calling the function directly cannot test errors that happen before the function is invoked.

## 12. Observing and Alerting on Errors in Production

Each error category needs dedicated metrics so operations teams know where to act:

| Metric/log field | Purpose |
|---|---|
| `conversion_error_total` | Detect producer/consumer contract mismatches |
| `business_rejection_total` | Track rejection decision counts by reason code |
| `infrastructure_error_total` | Track dependency and broker errors |
| `retry_attempt_total` | Detect flaky dependencies or retry storms |
| `dlq_message_count` | Track unprocessable messages |
| `oldest_dlq_message_age` | Identify long-standing backlogged errors |
| `consumer_lag` / queue backlog | Track ability to keep up with incoming data |
| `eventId`, `correlationId`, `causationId` | Look up an event and its business journey in logs/traces |

Use finite-cardinality reason codes for metric labels; never use event IDs, order IDs, or customer IDs as labels due to high cardinality. Detailed IDs should be recorded in structured logs and traces. When logging errors, include exception class, cause, binding, group, destination, and event ID if available; avoid logging tokens, passwords, or sensitive payloads.

Alerts should reflect actionable conditions: sudden spikes in conversion errors, business rejections exceeding thresholds, prolonged infrastructure errors, continuous retries, messages entering the DLQ, or growing consumer lag. Some business rejections are normal outcomes; set thresholds based on business expectations rather than alerting on every single rejection.

## 13. Principles for Choosing a Handling Policy

| Question | If the Answer Is "Yes" | Suggested Policy |
|---|---|---|
| Will running the same payload and same code again continue to fail? | Yes | Do not retry; quarantine or reject |
| Can the user fix the data and resubmit the request? | Yes | Return a rejected result with a reason code |
| Can the dependency self-recover within a short time? | Yes | Bounded retry, backoff, and jitter |
| Is it unknown whether the publish succeeded? | Yes | Retain event ID, check confirmation, and deduplicate |
| Has the message exhausted retries without being processed? | Yes | DLQ/quarantine, alert, and controlled replay |
| Is the error category still unclassified? | Yes | Record root cause, do not silently ignore |

A good policy must answer four things: whether the message is retried, the maximum number of attempts, where it is ultimately stored, and who is responsible for recovery. If any of those answers is missing, errors can turn into data loss or an unhandled backlog.

## 14. Practice Sequence and Completion Criteria

Create a `processOrder` consumer receiving events from `orders.created` and perform the following experiments:

1. Send valid JSON to verify the normal processing path.
2. Send malformed JSON and JSON with wrong field types to observe conversion errors.
3. Send a structurally valid payload with a negative `total` to verify business rejection.
4. Force the Customer API to time out to produce a transient infrastructure error.
5. Configure bounded retry with backoff; verify only transient errors are retried.
6. Make the dependency unavailable beyond the retry limit to verify the message is routed to a DLQ or recovery workflow.
7. Send a message with invalid credentials or a destination lacking permissions to verify configuration errors do not trigger tight retries.
8. Stop the consumer before ack/commit to observe redelivery.
9. Replay a fixed message and verify idempotency prevents duplicate side effects.
10. Monitor separate metrics for conversion, rejection, infrastructure, retry, and DLQ.

Complete this lesson when you can pinpoint which step an error occurred at; distinguish an unparseable payload from business-rejected data; distinguish both from a temporary dependency failure; and configure retry, DLQ, quarantine, logging, and corresponding tests for each category.

## 15. Official References

- [Spring Cloud Stream — Error handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html) — error channels, retry, and error handling in streams.
- [Spring Cloud Stream — Consumer properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html) — consumer binding retry configuration.
- [Spring Cloud Stream — Kafka binder DLQ](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/dlq.html) — Kafka binder dead-letter topic.
- [Spring Cloud Stream — RabbitMQ binder](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html) — Rabbit binder retry, republish, and dead-letter queue.
- [Spring Cloud Stream — Pulsar binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html) — Pulsar consumer properties and dead-letter policy.
- [Spring Messaging — Message conversion](https://docs.spring.io/spring-framework/reference/integration/spring-integration/message.html) — message abstraction, payload, and headers.
- [Project Reactor — Error handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html) — handling error signals in reactive pipelines.
