# Interaction Between maxAttempts, requeueRejected, and republishToDlq

When a message fails processing in the Spring Cloud Stream RabbitMQ Binder, the application can retry inside the listener, instruct RabbitMQ to return the message to the queue, or move the message to a Dead Letter Queue (DLQ). The three properties `maxAttempts`, `requeueRejected`, and `republishToDlq` govern different parts of this process. Understanding their order of application prevents infinite loops, unintended message drops, and DLQs failing to receive error data.

`maxAttempts` bounds how many times Spring Cloud Stream invokes the handler again during internal retry. `requeueRejected` determines whether the broker returns a rejected delivery back to the queue when internal retry is disabled or when the binder does not republish the message to the DLQ. `republishToDlq` determines whether the binder itself publishes failed messages to the DLQ with error metadata or lets RabbitMQ perform dead-lettering after rejection.

## 1. Three Properties Belong to Three Different Stages

| Property | Scope | Question it answers |
|---|---|---|
| maxAttempts | Internal Spring Cloud Stream retry | How many times at most is the handler invoked for a single delivery? |
| republishToDlq | How the binder handles a message after retries fail | Does the binder publish the failed message to the DLQ itself and attach error headers? |
| requeueRejected | How the listener rejects the final delivery | Does RabbitMQ return the delivery back to the original queue? |

A single message can undergo multiple handler invocations within the same delivery. Only if the final attempt still throws an exception do the binder and listener container decide to republish, reject, or requeue per configuration. Therefore, `maxAttempts` is not the total number of times RabbitMQ may deliver the message across its entire lifecycle.

## 2. Overall Processing Flow

~~~mermaid
flowchart TD
    A["RabbitMQ delivers message"] --> B["Spring Cloud Stream invokes handler"]
    B -->|Success| C["ACK delivery"]
    B -->|Throws exception| D{"Remaining maxAttempts?"}
    D -->|Yes| E["Backoff via RetryTemplate"]
    E --> B
    D -->|Exhausted or maxAttempts = 1| F{"republishToDlq?"}
    F -->|true and DLQ configured| G["Binder publishes to DLQ with error headers"]
    G --> H["Confirm publish then complete original delivery"]
    F -->|false| I{"requeueRejected?"}
    I -->|true| J["RabbitMQ requeues to original queue"]
    J --> A
    I -->|false| K["Reject without requeue"]
    K --> L{"Queue has DLX?"}
    L -->|Yes| M["RabbitMQ dead-letters to DLQ"]
    L -->|No| N["Message removed from queue"]
~~~

The diagram depicts the typical path for an imperative message handler. Special exceptions, transactions, publisher confirms, and broker DLQ settings can alter the final behavior; the sections below explain each case.

## 3. maxAttempts: Number of Handler Invocations

`maxAttempts` is the number of attempts to process a message, including the initial attempt. The default value for this consumer property in Spring Cloud Stream is 3. Setting `maxAttempts` to 1 disables internal retry.

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
          consumer:
            max-attempts: 4
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
~~~

With this configuration, the handler is invoked up to four times for a single delivery: the initial attempt plus three retries. The expected wait intervals are 1 second, 2 seconds, and 4 seconds. If additional retries occurred, the wait interval would grow by the multiplier without exceeding `back-off-max-interval`.

| Property | Meaning | Default |
|---|---|---:|
| max-attempts | Total processing attempts, including the first | 3 |
| back-off-initial-interval | Wait time before the first retry, ms | 1000 |
| back-off-max-interval | Upper bound on wait time, ms | 10000 |
| back-off-multiplier | Wait interval growth factor | 2.0 |
| default-retryable | Whether unlisted exceptions are retried | true |

Internal retry holds the listener thread during backoff intervals. For consumers with low concurrency or strict ordering requirements, this can stall other messages. If the failure is a prolonged disconnect or downstream outage, retrying directly inside the listener may hold deliveries for too long.

### 3.1. Retry Only Appropriate Error Types

Not every error can be resolved by retrying. Timeouts or transient connection failures may recover; schema errors, missing required fields, or business rule violations rarely change when re-invoked with the same data.

You can configure `retryable-exceptions` to classify errors:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          consumer:
            max-attempts: 4
            default-retryable: false
            retryable-exceptions:
              java.net.SocketTimeoutException: true
              org.springframework.dao.TransientDataAccessException: true
              java.lang.IllegalArgumentException: false
~~~

Exception names in the map are fully qualified class names. Verify the actual exception type thrown or wrapped by the framework. When `default-retryable` is false, only classes marked true are retried; classes marked false will not be retried.

Do not retry an operation with non-idempotent side effects if the previous attempt may have partially executed work. For instance, a payment or external record creation might have succeeded before the connection timed out. You need an idempotency key, unique constraint, or deduplication mechanism.

## 4. requeueRejected: Returning a Delivery to the Original Queue

`requeueRejected` is a Rabbit consumer property. When set to true, a rejected delivery can be returned by RabbitMQ to the original queue. When set to false, rejected deliveries are not requeued; if the queue has a Dead Letter Exchange (DLX), RabbitMQ can route the message to the DLQ. Without a DLX, the message is dropped from the queue.

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          consumer:
            max-attempts: 1
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              requeue-rejected: true
~~~

Here internal retry is disabled. When the handler throws an exception, the message is rejected and RabbitMQ returns it to the original queue. The message can be delivered immediately to the current consumer or another consumer.

`requeueRejected` introduces no wait interval. Consequently, if the error persists, the message can cycle rapidly:

1. Consumer receives message.
2. Handler throws exception.
3. RabbitMQ requeues message.
4. Consumer receives message again almost immediately.
5. Cycle repeats.

This loop consumes CPU, network, and broker resources; it can also keep the queue busy processing a poison message and starve other messages. Use direct requeue only when failures are extremely short-lived and explicit safeguards are in place.

### 4.1. Distinguishing Internal Retry from Broker Requeue

| Characteristic | Internal retry maxAttempts | Requeue via requeueRejected |
|---|---|---|
| Where executed | Spring Retry / listener | RabbitMQ broker |
| Attempt counting | maxAttempts includes the first attempt | Does not increment maxAttempts across internal retry cycles |
| Backoff | Configurable via back-off properties | No delay from requeueRejected |
| New delivery from broker | Not needed per internal retry | Causes redelivery from queue |
| Can loop infinitely? | Bounded by maxAttempts | Can loop continuously if errors persist |

For example, with `maxAttempts=3` and `requeueRejected=true`: Spring invokes the handler up to three times within the current delivery. If all three attempts fail, the final delivery can be requeued. When RabbitMQ redelivers it, a fresh `maxAttempts` cycle begins. Total handler invocations across the message's lifetime can thus become unbounded.

## 5. republishToDlq: Binder Publishes Failed Messages Explicitly

`republishToDlq` controls how the Rabbit binder transfers failed messages to the DLQ. When enabled, the binder uses a publisher to resend the message to the dead-letter destination and attaches failure details in headers, typically including the exception message and stack trace.

Useful headers:

| Header | Contents |
|---|---|
| x-exception-message | Message of the last exception |
| x-exception-stacktrace | Stack trace of the failure cause |
| x-original-exchange | Original exchange |
| x-original-routingKey | Original routing key |

Exact headers may depend on the binder version. Long stack traces can exceed RabbitMQ's `frame_max` limit; `frameMaxHeadroom` reserves space for other headers and the binder may truncate the stack trace if space is insufficient.

`republishToDlq` allows routing messages to the DLQ even when `maxAttempts=1`. Enabling this property does not require enabling internal retries.

To have the binder automatically create the DLQ and DLX, enable `autoBindDlq`. Setting `republishToDlq` without a valid DLQ topology does not replace declaring the target queue/exchange.

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
          consumer:
            max-attempts: 4
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              republish-to-dlq: true
              requeue-rejected: false
~~~

When all four attempts fail, the binder publishes the message to the DLQ with error metadata. The original message completes via the republish path; it is not returned to the original queue via `requeueRejected`.

### 5.1. republishToDlq Differs from Broker Dead-Lettering

Both mechanisms share the same DLQ destination, but take different paths:

| Characteristic | republishToDlq=true | republishToDlq=false |
|---|---|---|
| Who moves the message? | Binder publishes a new message to the DLQ | Binder rejects delivery; RabbitMQ applies DLX |
| Error headers | Binder can add exception message and stack trace | RabbitMQ adds dead-letter metadata such as x-death |
| Original message | Handled through binder DLQ publish path | Dead-lettered by broker per queue config |
| requeueRejected | Not the primary path once binder republish succeeds | Determines whether delivery returns to original queue |
| Topology dependency | Requires target DLQ the binder can publish to | Source queue requires valid DLX/routing |

Broker dead-lettering preserves messages via RabbitMQ's routing mechanism. The `x-death` header records reason, queue, exchange, routing key, and dead-letter count. `republishToDlq` is helpful when operations teams need the exception and stack trace directly on failed messages.

## 6. Combining the Three Properties by Strategy

### 6.1. Bounded Retry Followed by Binder DLQ Publish

This is a common choice when preserving stack traces and exception details is desired:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
          consumer:
            max-attempts: 4
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              republish-to-dlq: true
              requeue-rejected: false
~~~

Result: up to four handler invocations per delivery. Once exhausted, the binder republishes the message to the DLQ with exception information attached. `requeueRejected` is set to false to explicitly signal not returning failed messages to the source queue.

### 6.2. Bounded Retry Followed by RabbitMQ Dead-Lettering

If you want the broker to perform dead-lettering and preserve `x-death` metadata:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
          consumer:
            max-attempts: 4
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              republish-to-dlq: false
              requeue-rejected: false
~~~

Once internal retries are exhausted, the binder rejects the message without requeuing. RabbitMQ uses the DLX attached to the queue to move the message to the DLQ. If the DLX or routing key is wrong, the message may be dropped; verify topology before deploying.

### 6.3. No Internal Retry, Route Failures Straight to DLQ

When data errors cannot be fixed by retrying:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          consumer:
            max-attempts: 1
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              republish-to-dlq: true
              requeue-rejected: false
~~~

The handler is invoked once. If it throws an exception, the binder republishes the message to the DLQ. This strategy avoids repeating deterministic schema or validation failures that cannot self-heal.

### 6.4. Requeue Immediately on Failure

Use only when errors can clear very quickly, such as a transient resource that just restarted:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          consumer:
            max-attempts: 1
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              republish-to-dlq: false
              requeue-rejected: true
~~~

The message is requeued to the original queue and can be redelivered right away. This setup has no backoff, no requeue loop limit, and does not automatically route poison messages to a DLQ. Before using it, establish monitoring and loop termination conditions.

## 7. Configuration Decision Matrix

| maxAttempts | republishToDlq | requeueRejected | Expected behavior if final handler attempt still fails |
|---:|---|---|---|
| Greater than 1 | true | false | Internal retries; finally binder publishes to DLQ |
| Greater than 1 | false | false | Internal retries; finally reject without requeue so broker dead-letters if DLX exists |
| 1 | true | false | Single attempt; binder publishes to DLQ |
| 1 | false | false | Single attempt; reject without requeue; broker dead-letters if DLX exists |
| 1 | false | true | Single attempt per delivery; RabbitMQ requeues, may loop continuously |
| Greater than 1 | false | true | Internal retries first; finally requeue, starting a new delivery cycle |

The table assumes valid DLQ/DLX topology when dead-lettering is needed. Without a DLQ or DLX, rejecting without requeue can drop the message from the queue with nowhere to store it.

In current Rabbit binder documentation, `republishToDlq` is documented with a default of `true`; older docs/releases noted a default of `false`. `requeueRejected` defaults to `false` and `autoBindDlq` defaults to `false`. Because defaults have shifted across documentation generations, declare all three properties explicitly in your application and verify against your active Spring Cloud Stream BOM version.

## 8. How Should the DLQ Be Configured?

`autoBindDlq` tells the binder to declare the DLQ, dead-letter exchange, and matching binding. The default DLQ name is usually derived from the destination with a `.dlq` suffix; it can be customized with `deadLetterQueueName`. DLX and dead-letter routing key also have dedicated properties.

Example customizing the DLQ name:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              dead-letter-queue-name: orders.submitted.order-service.dlq
              republish-to-dlq: true
              requeue-rejected: false
~~~

Actual queue names and scopes can depend on prefix, destination, group, partitions, and binder version. Inspect created queues in the RabbitMQ Management UI or via `rabbitmqctl` rather than guessing names.

If infrastructure already created the DLX/DLQ via Terraform, Helm, or a separate provisioning workflow, you can use the existing topology settings and turn off the binder's corresponding declarations. You must then ensure exchanges, queues, and binding routing keys are created accurately; the binder cannot repair external topology if provisioning is disabled.

## 9. Broker Dead-Lettering and the x-death Header

When a message is rejected with `requeue=false` and the queue has a DLX, RabbitMQ routes the message to the dead-letter exchange. In AMQP 0-9-1, the broker records history in the `x-death` header. This header is a list of entries; each entry holds fields such as:

- queue: name of the queue that dead-lettered the message.
- reason: reason, such as `rejected`, `expired`, or `maxlen`.
- count: number of times dead-lettered for this queue/reason pair.
- exchange: original exchange at the time of dead-lettering.
- routing-keys: relevant routing keys.
- time: timestamp of dead-lettering.

`count` inside `x-death` is commonly represented as a long integer. Avoid unsafe casts or assuming the header always contains a single entry.

Example reading the header in a Consumer:

~~~java
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;

@Bean
Consumer<Message<OrderSubmitted>> inspectDeadLetterHistory() {
    return message -> {
        Object raw = message.getHeaders().get("x-death");
        if (raw instanceof List<?> deaths) {
            for (Object item : deaths) {
                if (item instanceof Map<?, ?> death) {
                    Object queue = death.get("queue");
                    Object reason = death.get("reason");
                    Object count = death.get("count");
                    System.out.printf(
                        "queue=%s reason=%s count=%s%n",
                        queue, reason, count
                    );
                }
            }
        }
    };
}
~~~

This snippet illustrates reading header data; in real applications, verify header mapping and data types after messages traverse the binder. `OrderSubmitted` is the example business payload type and must be declared in your application.

`x-death` is added by RabbitMQ only when the broker performs dead-lettering. If the binder republishes directly with `republishToDlq=true`, the message carries binder-generated exception metadata instead; do not treat `x-death` as a universal counter for all retry mechanisms.

## 10. Special Exceptions That Can Bypass the DLQ

Spring AMQP provides several exceptions that control acknowledge/requeue behavior:

| Exception | Behavior |
|---|---|
| AmqpRejectAndDontRequeueException | Rejects delivery without requeue; broker can dead-letter if queue has DLX |
| ImmediateRequeueAmqpException | Requests delivery requeue |
| ImmediateAcknowledgeAmqpException | Acknowledges message immediately, skipping DLQ and removing message from queue |

`ImmediateAcknowledgeAmqpException` can be used when the application intentionally decides a message should be dropped. Do not use it for business failures that require investigation because the message will not enter the DLQ.

If a handler throws `AmqpRejectAndDontRequeueException`, it explicitly indicates not to requeue even when general settings might suggest otherwise. If it throws `ImmediateRequeueAmqpException`, the message can return to the queue and loop. Use these exceptions only when you fully understand their interaction with `maxAttempts` and binder configuration.

## 11. Delayed Retry Using a DLQ and TTL

Internal retry holds the listener thread during backoff. Another option is to dead-letter a message to an intermediate queue with a TTL, and then let RabbitMQ dead-letter it back to the main queue once the TTL expires.

Flow:

~~~mermaid
flowchart LR
    A["Main queue"] -->|"Reject, requeue=false"| B["DLX"]
    B --> C[("Retry queue<br/>5s TTL")]
    C -->|"Message expires"| D["Retry DLX"]
    D --> E["Main queue"]
~~~

Conceptual configuration example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
          consumer:
            max-attempts: 1
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              republish-to-dlq: false
              requeue-rejected: false
              dlq-ttl: 5000
              dlq-dead-letter-exchange: ""
              dlq-dead-letter-routing-key: orders.submitted.order-service
~~~

This example assumes the source queue has the default name `orders.submitted.order-service`, with no prefix and without `queueNameGroupOnly`. An empty `dlq-dead-letter-exchange` selects the default exchange; `dlq-dead-letter-routing-key` must match the exact source queue name so expired messages route back. If you change the prefix or queue name, update the routing key accordingly. TTL alone does not create a retry cycle; the DLQ must have a dead-letter exchange/routing key returning messages to the source queue. If a message always fails, the loop can continue indefinitely. You can inspect `x-death` to cap cycles and then route the message to a parking-lot queue or retain it for investigation.

RabbitMQ quorum queues have built-in delivery limit and delayed retry support in compatible broker versions. Features and defaults depend on the RabbitMQ version; do not assume `requeueRejected=true` is always bounded by `x-death`. Check `delivery-count`, `delivery-limit`, and dead-lettering policies for your queue type.

## 12. Transactions and Reliability When Publishing to a DLQ

If a consumer is configured as `transacted`, the binder can enlist DLQ publishing inside the consumer's transaction. Per Rabbit binder documentation, since version 3.1.2, DLQ publishing can participate in the consumer transaction. If publishing fails, the transaction can roll back instead of silently completing the original delivery.

If the `ConnectionFactory` enables publisher confirms or returns, the binder can wait for confirms and inspect returned messages. If the broker returns a negative acknowledgement or a returned message, the binder can throw `AmqpRejectAndDontRequeueException` so RabbitMQ performs broker-native dead-lettering.

This matters when the application principal lacks publish permissions on the DLX or when the routing key mismatches. Grant required publish permissions, verify publisher confirms/returns, and monitor logs whenever DLQs fail to receive messages.

Do not treat a handler throwing an exception as proof that the message was saved into the DLQ. Verify the publish result or broker dead-lettering, especially when transactions are enabled.

## 13. DLQs Do Not Automatically Have a Reprocessing Consumer

The Rabbit binder can declare the DLQ and DLX, yet Spring Cloud Stream does not provide a single built-in policy for consuming or replaying every message in a DLQ. Applications and operations teams must decide whether to:

- Simply read and inspect failed messages.
- Fix data and replay manually.
- Automatically retry after a delay.
- Move to a parking-lot queue after maximum attempts.
- Discard messages when the error is confirmed unrecoverable and business-approved.

When building a DLQ consumer, preserve correlation ID, event ID, routing key, and investigative headers. When replaying, attach replay attempt metadata, operator identity, or replay timestamp; avoid erasing the original dead-letter trail.

## 14. Testing Interactions Among the Three Properties

Use a real RabbitMQ broker via Testcontainers or an integration test environment. The Test Binder checks function wiring, but does not fully verify broker requeue, DLX, and `x-death`.

Scenarios to verify:

1. Handler succeeds on first try: no retry, nothing in DLQ.
2. Handler fails twice then succeeds: invocation count is three, message is acknowledged after success.
3. Handler exhausts `maxAttempts` with `republishToDlq=true`: DLQ receives message with exception headers.
4. Handler exhausts `maxAttempts` with `republishToDlq=false` and `requeueRejected=false`: broker dead-letters message with `x-death`.
5. `maxAttempts=1`, `requeueRejected=true`: message redelivers to source queue; ensure test bounds prevent runaway loops.
6. No DLX/DLQ configured and reject without requeue: verify message is dropped from queue to recognize message-loss risk.
7. DLQ publish rejected due to permissions or routing: verify error is logged and delivery is not falsely acknowledged.
8. `ImmediateAcknowledgeAmqpException`: verify message is skipped and absent from DLQ.
9. Non-retryable exception: verify handler is called only once before entering final handling.
10. Large payload message: verify stack trace header does not exceed `frame_max` or get unexpectedly truncated.

A test counting handler invocations can use a counter in a stub service. For DLQ tests, inspect the actual queue and message headers; do not just assert error lines in logs.

## 15. Monitoring and Operations

In production, monitor:

| Metric | Meaning |
|---|---|
| Internal retry count | Whether transient failures are rising |
| Redelivered delivery count | Whether messages are repeatedly redelivered by the broker |
| Main queue depth | Whether consumers keep pace with traffic |
| DLQ depth | How many messages require investigation |
| DLQ ingress rate | New failures occurring over time |
| DLQ publish failure rate | Whether the binder succeeds in sending failed messages |
| Parking-lot message count | Messages that exceeded retry policies |
| Average and p95/p99 processing time | Whether backoff and retries are stalling consumers |

Do not watch main queue depth alone. A main queue can stay shallow while messages continuously requeue, driving up CPU and logs. Combine redelivered counts, retry counts, DLQ rate, and exception types to spot loops.

Stack traces and exception messages can contain class names, queries, or input data. Restrict DLQ read access, retention periods, and log contents according to security policies. Never put tokens, passwords, or personal data into diagnostic headers.

## 16. Configuration Selection Checklist

- [ ] Classify which errors can be retried and which should go straight to the DLQ.
- [ ] Set `maxAttempts` explicitly; remember it includes the first attempt.
- [ ] Choose backoff matching dependency recovery times.
- [ ] Enable `autoBindDlq` if you want the binder to create the DLX/DLQ.
- [ ] Explicitly set `republishToDlq` true or false based on metadata needs.
- [ ] Set `requeueRejected=false` for terminal failure paths that should dead-letter.
- [ ] Use `requeueRejected=true` only with a clear rationale and loop bounds.
- [ ] Verify binder version because `republishToDlq` defaults changed across docs/releases.
- [ ] Verify publish permissions, DLX, routing key, and DLQ queue.
- [ ] Test successful messages, exhausted retries, requeue, and dead-lettering.
- [ ] Maintain an investigation, replay, or parking-lot workflow for DLQs.
- [ ] Monitor retries, redeliveries, DLQ depth, and DLQ publish errors.

## Official References

- [Spring Cloud Stream RabbitMQ Binder Reference Guide](https://docs.spring.io/spring-cloud-stream-binder-rabbit/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html): `autoBindDlq`, `maxAttempts`, `requeueRejected`, `republishToDlq`, retry, and DLQ properties.
- [Spring Cloud Stream - Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html): `RetryTemplate`, `maxAttempts`, backoff, and exception classification.
- [Spring Cloud Stream - Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html): consumer retry properties and default values.
- [RabbitMQ - Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): dead-letter routing, `x-death`, and dead-lettering causes.
- [RabbitMQ - Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues): quorum queue delivery limits, redelivery, and delayed retries.