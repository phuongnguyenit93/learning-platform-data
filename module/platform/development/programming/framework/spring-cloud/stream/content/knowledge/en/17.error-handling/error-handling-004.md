# Choosing Retryable and Non-Retryable Exceptions

In an event-driven system, a message can fail for many reasons: a dependent service is temporarily unavailable, the network times out, the data is invalid, or a business rule rejects the request. If every error is retried, the application may loop pointlessly over bad data, generate heavy load during an incident, or execute a business side effect multiple times. If transient errors are not retried, messages can be routed to error handling even though a brief wait would have resolved the issue.

Spring Cloud Stream allows configuring retry policies per consumer binding and classifying exceptions using `retryableExceptions` together with `defaultRetryable`. This lesson explains how to distinguish transient errors from permanent errors, choose attempt counts and backoff, route unprocessable messages to a dead-letter queue (DLQ), and test behavior with Kafka, RabbitMQ, or Pulsar binders.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish recoverable transient exceptions from exceptions that cannot be recovered by retrying.
- Choose which exceptions are retried and which are excluded from retry based on business context.
- Configure `maxAttempts`, `backOffInitialInterval`, `backOffMaxInterval`, and `backOffMultiplier`.
- Use `retryableExceptions` and `defaultRetryable` to classify errors by exception type.
- Understand the sequence of retry, recovery, and DLQ in consumer processing.
- Distinguish imperative consumer retries from retries in a reactive pipeline.
- Design idempotency, logs, and metrics to prevent duplicate side effects.
- Test retryable errors, non-retryable errors, and behavior after attempts are exhausted.

## 1. Why Classify Exceptions?

Retries help when the same operation is likely to succeed if attempted again after a pause. For example, an inventory service is temporarily unresponsive or an auxiliary broker connection briefly dropped. In contrast, a message containing an invalid order code or violating a business rule usually cannot become valid simply by being sent again.

Errors can be divided into two main groups:

| Error Group | Characteristics | Generally Appropriate Action |
|---|---|---|
| Transient | Cause may resolve on its own after some time | Bounded retry with backoff |
| Permanent / non-recoverable via retry | Invalid data, permissions, or business rules | Do not retry; send to DLQ or error-handling flow |

Classification should be based on root cause and recoverability, not simply whether the exception is checked or unchecked. A `RuntimeException` can be a transient error; a checked exception can represent permanently invalid data.

### Examples of Errors That Are Usually Retryable

- Timeout when calling an inventory or payment service, provided the operation can be safely re-invoked.
- Temporary database connection interruption.
- Dependent service returns HTTP 503 or 429 with an appropriate wait policy.
- Temporary leader/partition errors in distributed infrastructure.
- Schema registry temporarily unreachable while the schema has already been validly published.

### Examples of Errors That Usually Should Not Be Retried

- Input data missing a required field or having an invalid format.
- Order violating a business rule, such as a negative total amount.
- Unsupported currency or event type.
- Incompatible schema or payload unreadable because the producer sent the wrong wire format.
- Caller lacking permission to perform the operation.
- Permanently misconfigured settings, such as invalid endpoints or credentials.

There are contextual exceptions: HTTP 401 caused by an expired token can recover after refreshing the token; HTTP 429 can be retried after the server-requested delay; a schema registry timeout can be transient, whereas a schema rejected by the registry due to compatibility violations is usually permanent. Classify according to the specific root cause.

## 2. Designing Exceptions Around Recoverability

Use exceptions that clearly express the reason and recoverability. For example:

~~~java
public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}

public class UnsupportedCurrencyException extends RuntimeException {
    public UnsupportedCurrencyException(String message) {
        super(message);
    }
}

public class TemporaryInventoryException extends RuntimeException {
    public TemporaryInventoryException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class RemoteServiceTimeoutException extends RuntimeException {
    public RemoteServiceTimeoutException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Exception names help readers understand why processing failed. For example:

- `InvalidOrderException`: syntactically valid message that violates business rules; retrying does not change the data.
- `UnsupportedCurrencyException`: currency not supported by the system; data or contract needs fixing.
- `TemporaryInventoryException`: inventory service temporarily unavailable; can be retried.
- `RemoteServiceTimeoutException`: response not received in time; requires evaluating whether the remote operation may already have completed.

Do not catch every exception and convert it into a generic exception such as `RuntimeException` if doing so loses classification info. If wrapping is necessary, preserve the cause so the classifier or error handler can inspect the root cause.

### Wrapper Exceptions and Causes

In messaging applications, errors may be wrapped by `MessagingException`, `CompletionException`, or client exceptions. The outermost exception is not necessarily the cause to classify on. Inspect the cause chain and test how the binder/`RetryPolicy` receives the actual exception.

If a `TemporaryInventoryException` is wrapped inside a generic exception and the classifier only checks the outermost type, the policy may not work as expected. For systems needing root-cause classification, a custom classifier or retry policy can be used; verify the semantics of the Spring Retry and Spring Cloud Stream versions in use.

## 3. Configuring Retry on a Consumer Binding

Spring Cloud Stream provides consumer properties to control retry:

| Property | Meaning |
|---|---|
| `maxAttempts` | Maximum total handler invocations, including the initial attempt |
| `backOffInitialInterval` | Wait interval before the first retry, in milliseconds |
| `backOffMaxInterval` | Upper bound of the wait interval between retries |
| `backOffMultiplier` | Multiplier to increase the wait interval after each failure |
| `defaultRetryable` | Whether unlisted exceptions are classified as retryable by default |
| `retryableExceptions` | Map from fully qualified exception class name to true/false |

Example order-processing consumer configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            maxAttempts: 4
            backOffInitialInterval: 500
            backOffMaxInterval: 5000
            backOffMultiplier: 2.0
            defaultRetryable: false
            retryableExceptions:
              com.example.order.TemporaryInventoryException: true
              com.example.order.RemoteServiceTimeoutException: true
              com.example.order.InvalidOrderException: false
              com.example.order.UnsupportedCurrencyException: false
~~~

This configuration means:

- The handler is invoked at most four times: one initial attempt and up to three retries.
- Wait intervals grow exponentially starting from 500 ms, capped at 5,000 ms.
- Only exceptions marked `true` are retried.
- Exceptions absent from the map are not retried by default because `defaultRetryable: false`.
- Business errors marked `false` proceed directly to recovery/error handling.

Setting `defaultRetryable: false` is a conservative approach when you want to retry only explicitly identified failures. If the application chooses `defaultRetryable: true`, unlisted exceptions are treated as retryable by default, which can cause data errors or programming bugs to loop repeatedly.

### How Is `maxAttempts` Calculated?

`maxAttempts` includes the initial invocation. For example:

| maxAttempts | Maximum Executions | Maximum Retries |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 2 | 1 |
| 3 | 3 | 2 |
| 4 | 4 | 3 |

Set `maxAttempts: 1` to perform no retries in this consumer policy. That does not mean the rest of the system cannot retry at another layer; binder clients, service methods, or producers may have their own policies.

## 4. Understanding Backoff and the Retry Budget

If retries happen back-to-back with no pause, many consumers can simultaneously hammer a struggling service. This creates a retry storm and makes recovery harder.

Backoff increases the wait time after each failure. With the configuration:

~~~yaml
consumer:
  maxAttempts: 4
  backOffInitialInterval: 500
  backOffMaxInterval: 5000
  backOffMultiplier: 2.0
~~~

The illustrative wait intervals between attempts are:

| Retry Attempt | Expected Wait Interval |
|---:|---:|
| 1 | 500 ms |
| 2 | 1,000 ms |
| 3 | 2,000 ms |

Actual duration depends on the retry policy and the processing time of each invocation. `backOffMaxInterval` caps the maximum wait interval. A system may need an overall retry budget to ensure processing duration stays within SLA.

### When Is Jitter Needed?

If many consumers fail at the same moment, deterministic backoff on the same schedule can cause them to retry in lockstep. Jitter adds random variance to wait times to spread out load. The basic backoff properties above should not be assumed to enable jitter automatically; if needed, use a custom retry policy or a jitter-supporting mechanism compatible with your version.

### Do Not Retry for Too Long

Retry duration must be weighed alongside:

- Message retention time on the broker.
- Business processing SLA.
- Downstream call timeouts.
- Number of consumers and concurrent retry traffic.
- Ability to process older messages after the system recovers.

If a message cannot be processed within the allowed time budget, routing it to an error flow for investigation is usually better than keeping the consumer tied up for a long time.

## 5. Classifying Exceptions with `retryableExceptions`

`retryableExceptions` is a map from fully qualified class name to boolean. `true` marks the exception as retryable; `false` disables retry for that exception.

Minimal example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        inventory-in-0:
          consumer:
            defaultRetryable: false
            retryableExceptions:
              com.example.InventoryUnavailableException: true
              com.example.InvalidSkuException: false
~~~

When `InventoryUnavailableException` occurs, the consumer applies the retry policy and backoff. When `InvalidSkuException` occurs, the consumer does not re-invoke the handler under that retry policy and instead moves to the error-handling/recovery step.

If an exception is not in the map, `defaultRetryable` decides the behavior. Explicitly declare important errors and write tests using real exceptions, especially when errors are wrapped by frameworks or client libraries.

### Sample Decision Table

| Exception | Classification | Reason | Policy |
|---|---|---|---|
| `TemporaryInventoryException` | Retryable | Inventory service temporarily unavailable | Bounded retry |
| `RemoteServiceTimeoutException` | Conditional | May time out even though remote operation completed | Retry if operation is idempotent |
| `InvalidOrderException` | Non-retryable | Invalid business data | Send to DLQ or handle manually |
| `UnsupportedCurrencyException` | Non-retryable | Contract does not support currency | Do not retry |
| `SchemaIncompatibleException` | Non-retryable | Writer/reader schemas incompatible | Investigate producer and schema |
| `SchemaRegistryUnavailableException` | Retryable | Registry temporarily unreachable | Retry with backoff |
| `AuthenticationException` | Usually non-retryable | Wrong credentials or permissions | Fix configuration/permissions |
| `RateLimitExceededException` | Conditional | Service requests throttling down | Retry per Retry-After or suitable backoff |

Do not use this table as a substitute for actual verification. For example, a timeout after a write operation can leave an ambiguous outcome: the server committed, but the client missed the response. Retrying then can create duplicate transactions if the service is not idempotent.

## 6. Consumer Example and Error Classification

An imperative consumer can let exceptions escape the function so the binder applies the retry policy:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderConsumerConfiguration {

    @Bean
    Consumer<OrderCreated> processOrder(OrderService orderService) {
        return event -> orderService.process(event);
    }
}
~~~

The business service should throw meaningful exceptions:

~~~java
public class OrderService {

    private final InventoryClient inventoryClient;

    public OrderService(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    public void process(OrderCreated event) {
        if (event.total().signum() <= 0) {
            throw new InvalidOrderException("Total amount must be greater than 0");
        }

        try {
            inventoryClient.reserve(event.orderId());
        } catch (InventoryUnavailableException ex) {
            throw new TemporaryInventoryException(
                "Inventory service temporarily unavailable",
                ex
            );
        }

        // Perform next business step after reservation succeeds.
    }
}
~~~

When `InvalidOrderException` occurs, do not retry. When `TemporaryInventoryException` occurs, retry per configuration. If the service catches all exceptions and merely logs and returns normally, the binder will treat the message as successfully processed; do not swallow exceptions if you want retry or DLQ.

### Do Not Use Catch-All to Turn Failures into Success

Pattern likely to cause message loss:

~~~java
@Bean
Consumer<OrderCreated> unsafeConsumer(OrderService service) {
    return event -> {
        try {
            service.process(event);
        } catch (Exception ex) {
            log.error("Failed to process order", ex);
        }
    };
}
~~~

The consumer above throws nothing outward. The binder receives no failure signal to trigger retry or recovery. If you want to log, log and rethrow the exception, or route the error through an explicitly designed recovery mechanism.

## 7. Retry, Recovery, and Dead-Letter Queue

A consumer processing cycle typically follows these steps:

1. The binder delivers the message to the consumer.
2. The function or handler executes business logic.
3. If the handler throws an exception, the retry policy classifies the exception.
4. If the exception is retryable and attempts remain, the handler is invoked again after the backoff pause.
5. If the exception is non-retryable or attempts are exhausted, the system moves to recovery.
6. If a DLQ is configured and supported by the binder, the message is routed to the dead-letter destination; otherwise behavior depends on error channels, acknowledgment, and binder settings.

~~~mermaid
flowchart TD
    A["Receive message"] --> B["Invoke consumer"]
    B --> C{"Processing succeeded?"}
    C -->|Yes| D["Complete / acknowledge per binder"]
    C -->|No| E{"Exception retryable?"}
    E -->|Yes| F{"Attempts remaining?"}
    F -->|Yes| G["Backoff"]
    G --> B
    F -->|No| H["Recovery / error handling"]
    E -->|No| H
    H --> I{"DLQ configured?"}
    I -->|Yes| J["Send message to DLQ"]
    I -->|No| K["Error channel or binder behavior"]
~~~

A DLQ isolates messages that cannot be processed automatically. A DLQ allows the main consumer to continue processing other messages while preserving failing data for investigation and replay after remediation.

Do not treat a DLQ as a place where messages are automatically repaired or successfully processed. Establish an operational workflow to classify causes, fix data or services, and then perform controlled replay.

## 8. Binder-Specific DLQ Configuration

The shared retry policy sits on the consumer binding; creating and sending to a DLQ is the binder-specific part.

### Kafka Binder

The Kafka binder supports DLQ for consumers with a group. Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            maxAttempts: 4
            defaultRetryable: false
            retryableExceptions:
              com.example.TemporaryInventoryException: true
              com.example.InvalidOrderException: false
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enableDlq: true
              dlqName: orders.order-processor.dlq
~~~

In the example, messages that are not retried or have exhausted attempts are sent to the DLQ according to Kafka binder capabilities and settings. A consumer group must be declared so the binder can identify the processing stream and corresponding DLQ. The DLQ name can be specified explicitly; if omitted, the binder uses its version's default naming convention.

In operations, monitor the DLQ topic alongside the source topic. With Kafka, metadata such as original topic, partition, and offset is useful for tracing. Verify the DLQ partition count and write permissions for the binder's internal producer.

### RabbitMQ Binder

The Rabbit binder provides dedicated properties to declare dead-letter exchanges/queues and republish behavior. Illustrative example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            maxAttempts: 4
            defaultRetryable: false
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              autoBindDlq: true
              republishToDlq: true
~~~

`autoBindDlq` instructs the binder to create/bind the dead-letter topology per configuration. `republishToDlq` allows the binder to republish the message along with error metadata as supported by the binder. Exchange, queue, routing key, and permission properties must be cross-checked with your Rabbit binder version.

### Pulsar Binder

Pulsar supports retry-letter topics and dead-letter topics via consumer/client policies. The binder may provide dedicated configuration to declare redelivery counts, retry topic names, and dead-letter topic names. Exact settings depend on the Spring Cloud Stream Pulsar binder and Spring for Apache Pulsar versions.

Do not copy Kafka's `enableDlq` or Rabbit's `autoBindDlq` properties to Pulsar. Consult the binder documentation, verify the subscription type and redelivery policy, and test that messages move to the retry/DLQ topic after the expected number of attempts.

### When No DLQ Is Configured

Without a DLQ, a message after failed retries may be sent to an error channel, rejected, requeued, or handled by the binder/container mechanism. There is no single universal behavior across all brokers and versions. Clarify the failure path of the binder you are using to avoid infinite loops or unexpected message drops.

## 9. Retries in Reactive Functions

Reactive functions handle errors as `onError` signals in Reactor. `retryWhen` can be used to retry an inner publisher. For multi-message streams, place retry inside each item's processing if the goal is to retry that specific message.

Example:

~~~java
import java.time.Duration;
import java.util.function.Function;

import reactor.core.publisher.Flux;
import reactor.util.retry.Retry;

@Bean
Function<Flux<OrderCreated>, Flux<ProcessedOrder>> processOrders(
        ReactiveOrderService service) {

    return events -> events.flatMap(
        event -> service.process(event)
            .retryWhen(
                Retry.backoff(3, Duration.ofMillis(200))
                    .maxBackoff(Duration.ofSeconds(2))
                    .filter(this::isTransient)
            ),
        8
    );
}
~~~

In the example:

- `service.process(event)` returns a publisher for each message.
- `retryWhen` is placed inside `flatMap`, so it retries that message's publisher.
- At most three retries after the initial subscription per Reactor Retry semantics.
- `filter(this::isTransient)` only retries exceptions classified as transient.
- `flatMap(..., 8)` caps concurrency at eight active inner publishers.

Do not arbitrarily wrap the entire `Flux` in retry if you only intend to retry a single message. Stream-level retry can resubscribe to the source and reprocess multiple previously emitted items.

With reactive functions, binders and versions may have distinct acknowledgment/retry semantics. Do not assume consumer binding `maxAttempts` and Reactor `retryWhen` always stack or replace one another identically. Test end-to-end to know when messages are acknowledged, which errors terminate the subscription, and how DLQ is triggered.

## 10. Avoiding Nested Retries and Retry Storms

A service method may use Spring Retry or `@Retryable` on its own, while the consumer binding also has `maxAttempts`. If both layers retry, the actual invocation count multiplies.

For example, the consumer allows four attempts and the service method allows three total calls per consumer run. One message can trigger up to twelve service calls. When many messages fail, request volume surges rapidly.

Assign one primary retry owner for each operation. If multi-layer retry is necessary, compute total call counts and wait durations to avoid blowing past the retry budget. Principles to reduce retry storms:

- Bound the total number of attempts.
- Use increasing backoff.
- Use jitter when multiple instances might retry simultaneously.
- Honor `Retry-After` or downstream service quotas.
- Limit retry concurrency.
- Stop retrying once an error is known to be permanent.
- Monitor retry counts and DLQ ingress rate.

## 11. Idempotency and Ambiguous Outcomes

Retries can re-invoke a handler after a previous attempt caused an external side effect whose response was lost. For example, the payment service recorded the transaction, but the consumer timed out before receiving the response. Resending the payment command without an idempotency key can create a duplicate transaction.

A business message should carry a stable identifier, such as `eventId`. The receiving service can store the idempotency key alongside the processing outcome and return the previous result when receiving the same key again.

Useful practices:

- Use `eventId` or a business operation ID as the idempotency key.
- Enforce a unique constraint where processed state is stored.
- Use transactional outbox/inbox when coordinating database and broker state.
- Do not treat a timeout as proof that the remote operation did not happen.
- Distinguish errors before commit from errors after commit where the response was lost.

A retry policy handles re-attempts; idempotency protects business side effects when the same operation executes multiple times. The two mechanisms complement each other.

## 12. Testing Exception Classification

Build a test matrix for exception types:

| Scenario | Expected Invocation Count | Result |
|---|---:|---|
| Handler succeeds | 1 | Message processed |
| Retryable exception, succeeds next time | 2 or more depending on recovery | Message processed after retry |
| Retryable exception, always fails | Up to `maxAttempts` | Routes to recovery/DLQ |
| Non-retryable exception | 1 | Routes to recovery/DLQ immediately |
| Unlisted exception, `defaultRetryable=false` | 1 | Not retried |
| Unlisted exception, `defaultRetryable=true` | Per `maxAttempts` | Retried by default |
| Wrapper exception containing retryable cause | Per actual classifier | Requires verifying cause traversal |

### Unit Testing the Classifier

You can test the application's classification helper separately:

~~~java
boolean isTransient(Throwable error) {
    Throwable cause = error;

    while (cause != null) {
        if (cause instanceof TemporaryInventoryException
                || cause instanceof RemoteServiceTimeoutException) {
            return true;
        }
        cause = cause.getCause();
    }

    return false;
}
~~~

This is an example classifier for a reactive pipeline or application logic. If using Spring Cloud Stream's `retryableExceptions`, test the binding configuration with actual exceptions instead of assuming the map automatically follows the exact cause-traversal logic above.

### Binding and Broker Integration Tests

Use the test binder or a real broker to verify:

1. The consumer binding has the right name and group.
2. `maxAttempts` produces the expected invocation count.
3. Backoff occurs within expected bounds.
4. Non-retryable exceptions are not re-invoked.
5. Retryable exceptions are re-invoked and stop upon success or exhaustion.
6. Messages after recovery route to the right DLQ/error channel.
7. Error metadata and original payload remain sufficient for investigation.
8. Replay does not create duplicate business side effects.

The test binder is useful for function logic and bindings, but DLQ, acknowledgment, and redelivery behaviors need broker integration tests for Kafka, RabbitMQ, or Pulsar.

## 13. Operating the DLQ and Replay

A DLQ needs a concrete operational procedure. A message in the DLQ should be investigated using:

- Original payload and `eventId`.
- Source destination, group, and binder.
- Exception class, message, and failure timestamp.
- Retry count and processing duration.
- Broker metadata such as topic/partition/offset or routing/subscription if available.
- Application version and message schema.

Do not place secrets, access tokens, or sensitive data into error headers or logs. Stack traces can contain file paths, queries, or internal data; control access to DLQs and logs.

Suggested replay workflow:

1. Classify messages in the DLQ.
2. Identify the cause: bad data, schema, permissions, dependent service, or application bug.
3. Fix the root cause before replaying.
4. Verify payloads remain compatible with the current schema.
5. Select the subset of messages to replay and record their `eventId`s.
6. Replay into the appropriate stream with rate control.
7. Verify results and prevent duplicate processing.
8. Retain an audit trail of the replay operation.

Do not configure a consumer to read from a DLQ and send the same message right back into the same DLQ without a stopping condition; this can create an infinite loop.

## 14. Common Mistakes When Choosing Retry Exceptions

| Symptom | Possible Cause | How to Fix |
|---|---|---|
| Data errors retried multiple times | `defaultRetryable` is still true or exceptions unclassified | Set an appropriate default and mark business errors false |
| Timeout errors not retried | Actual exception is wrapped or mismatches map | Inspect root cause and classifier |
| Consumer calls service too many times | Nested retries in binder and service | Compute total calls, choose one layer to own retry |
| Messages go straight to DLQ | Exception classified non-retryable or `maxAttempts=1` | Check map and attempt count |
| Messages loop endlessly | Binder requeue/retry lacks proper bounds | Define failure path, `maxAttempts`, and DLQ |
| DLQ is not created | DLQ config not enabled or missing group/permissions | Check binder properties and topology |
| Messages reach DLQ missing metadata | Binder not republishing or header mapping misconfigured | Check republish capability and header mapping |
| Retry storm when service recovers | Synchronized backoff, excessive concurrency | Add jitter, reduce concurrency, and bound retries |
| Duplicate transactions executed | Retry after timeout without idempotency | Use `eventId`/idempotency key and inbox/outbox |
| Reactive stream stops after one error | Error emitted at full `Flux` level | Classify and handle errors per message where appropriate |

When investigating, grab the actual exception from logs, trace the cause chain, check the map and default, count attempts, and verify the binder's recovery path. Do not assume a message will enter the DLQ just by looking at YAML configuration.

## 15. Practice Lab: Classifying Order-Processing Errors

Create a `processOrder` consumer reading from destination `orders`:

1. Declare `InvalidOrderException`, `UnsupportedCurrencyException`, `TemporaryInventoryException`, and `RemoteServiceTimeoutException`.
2. Update the service to throw the right exception for each cause.
3. Configure `maxAttempts: 4`, initial backoff 500 ms, max 5,000 ms, and multiplier 2.
4. Set `defaultRetryable: false`.
5. Mark the two transient exceptions as retryable.
6. Mark the two business exceptions as non-retryable.
7. Send a valid message and verify the handler runs once.
8. Simulate the inventory service failing temporarily then recovering; verify the consumer retries and succeeds.
9. Send an order with invalid data; verify the handler does not retry.
10. Keep the inventory service failing continuously; verify invocations do not exceed `maxAttempts`.
11. Enable binder DLQ and verify failed messages arrive at the expected destination.
12. Replay a message after fixing the root cause and verify idempotency.
13. Test an exception wrapped in `MessagingException` to inspect how the classifier identifies the cause.

Acceptance Checklist:

| Item | Result to Verify |
|---|---|
| Exception taxonomy | Clear transient/permanent classification |
| `defaultRetryable` | Value matches application policy |
| `retryableExceptions` | Class names and booleans accurate |
| `maxAttempts` | Counts initial attempt as well |
| Backoff | Increases progressively and is capped |
| Non-retryable | Handler is not re-invoked |
| Exhausted retry | Routes to recovery properly |
| DLQ | Message and metadata sufficient for investigation |
| Idempotency | Replay produces no duplicate side effects |
| Observability | Metrics present for retry, error, and DLQ |

## Conclusion

Choosing whether an exception is retried is a decision about business recoverability. Transient errors can be retried with bounded attempts and backoff; data, permission, or business-rule errors should generally proceed straight to recovery/DLQ for investigation.

In Spring Cloud Stream, use `retryableExceptions` and `defaultRetryable` for explicit classification, set `maxAttempts` and backoff within your retry budget, and verify binder-specific DLQ behavior. Combine retry with idempotency, test wrapper exceptions, and watch for retry storms so messages are handled safely when Kafka, RabbitMQ, or Pulsar encounter failures.

## References

- [Spring Cloud Stream – Consumer Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream – Kafka Binder and DLQ](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder.html)
- [Spring Cloud Stream – Rabbit Binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
- [Project Reactor – Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
