# Error Header Limits and frameMaxHeadroom

When a Spring Cloud Stream consumer using the RabbitMQ binder fails to process a message, the binder can send the message to a Dead Letter Queue (DLQ). If `republishToDlq` is enabled, the binder republishes the message to the DLQ and attaches error metadata, including the exception message and stack trace. Stack traces are very helpful when investigating incidents, yet they can grow to tens or hundreds of kilobytes if exceptions are deeply nested, have many frames, or pass through many library layers.

RabbitMQ limits AMQP frame sizes via `frame_max` negotiated on the connection. Message headers must fit within appropriate frame limits. If a stack trace is too large, it can consume nearly all header space and prevent the message from being republished as expected. The Spring Cloud Stream Rabbit binder provides the `frameMaxHeadroom` property to reserve a number of bytes for other headers when sizing the stack trace added to a DLQ message.

This property defaults to **20,000 bytes**. It only adjusts the stack trace portion that the binder appends to error headers; it does not alter RabbitMQ's `frame_max`, nor does it limit business payload size.

## 1. Why Can Error Headers Exceed Frame Limits?

An AMQP message has a properties/headers section and a body section. RabbitMQ transmits messages over AMQP frames; `frame_max` limits the frame size used on a connection. For normal messages, business headers such as `contentType`, `correlationId`, `eventType`, or `tenantId` are usually quite small.

When the binder republishes a failed message to a DLQ, it can attach headers describing the exception, such as:

- `x-exception-message`: error message.
- `x-exception-stacktrace`: stack trace of the final failure.

Stack traces can grow quickly when:

- Exceptions are wrapped across many `cause` layers.
- An error occurs inside a library with very deep stack traces.
- The exception message contains large input payloads or verbose content.
- Frameworks add numerous asynchronous, reflection, or proxy frames.
- A batch or chained failure produces long diagnostic details.

If the stack trace header plus the headroom reserved for other headers exceeds `frame_max`, the binder truncates the stack trace and logs a `WARN` message. The goal is to preserve space for other headers rather than letting the stack trace consume the entire limit.

## 2. What Is frameMaxHeadroom?

`frameMaxHeadroom` is the number of bytes the RabbitMQ binder reserves for other headers when determining how much of a stack trace can be added to DLQ message headers. The default value is `20000`.

You can visualize the budget conceptually:

```text
connection frame_max
  ├── frameMaxHeadroom reservation for other headers
  └── remaining space available for the stack trace header
```

This is a conceptual model to understand how the limit works, not a formula replacing actual header measurement. Actual size also depends on existing headers and how AMQP/Spring AMQP encodes message properties.

| Property | Meaning |
| --- | --- |
| `frame_max` | AMQP frame size limit negotiated between the client and RabbitMQ on the connection |
| `frameMaxHeadroom` | Bytes reserved for other headers when the binder adds a stack trace to a DLQ message |
| `x-exception-stacktrace` | Header containing the stack trace added by the binder when republishing failed messages |
| Message body | Business payload, carried in content body frames; not directly capped by `frameMaxHeadroom` |

**Key point:** increasing `frameMaxHeadroom` reserves more bytes for other headers, leaving less space for the stack trace. If stack traces are getting truncated for being too long, the primary fix is usually raising RabbitMQ's `frame_max` appropriately or shrinking the stack trace—not blindly increasing `frameMaxHeadroom`.

## 3. When Does This Property Take Effect?

`frameMaxHeadroom` is a RabbitMQ binder consumer property. It applies when the binder republishes failed messages to a DLQ and attaches the stack trace to headers.

Common conditions:

1. The input binding uses the RabbitMQ binder.
2. The consumer has DLQ configuration, such as `autoBindDlq` enabled or pre-provisioned dead-letter infrastructure.
3. `republishToDlq` is enabled so the binder resends the message with error metadata.
4. The stack trace is added to headers and must be bounded to fit within the frame.

If `republishToDlq` is disabled, the binder can reject the message so RabbitMQ routes the original message via the dead-letter exchange. In that case, the binder does not republish the message with a stack trace via this mechanism, so `frameMaxHeadroom` does not control any appended stack trace header.

Current Rabbit binder documentation notes `republishToDlq` defaults to `true`, while `autoBindDlq` defaults to `false`. Configure both explicitly rather than relying on defaults when designing production error flows.

## 4. Configuring Per Input Binding

Example of an order-processing application with binding `processOrder-in-0`:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-service
          content-type: application/json
          consumer:
            maxAttempts: 3
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              autoBindDlq: true
              republishToDlq: true
              frameMaxHeadroom: 20000
```

In this configuration:

- `destination` maps to the Rabbit binder exchange.
- `group` defines a stably named consumer queue.
- `maxAttempts: 3` allows up to three processing attempts per delivery, including the initial attempt.
- `autoBindDlq: true` tells the binder to declare the DLQ and dead-letter exchange per binder conventions.
- `republishToDlq: true` tells the binder to republish failed messages with error metadata.
- `frameMaxHeadroom: 20000` reserves 20,000 bytes for other headers when sizing the appended stack trace.

Rabbit-specific properties go under `spring.cloud.stream.rabbit.bindings.<bindingName>.consumer`. Do not place `frameMaxHeadroom` under `spring.cloud.stream.bindings.<bindingName>.consumer`, as that is the generic consumer property namespace and not where Rabbit binder properties are declared.

## 5. Default Configuration Across Multiple Bindings

If several Rabbit input bindings need the same value, you can set a default at the Rabbit binder level:

```yaml
spring:
  cloud:
    stream:
      rabbit:
        default:
          frameMaxHeadroom: 24000
        bindings:
          processOrder-in-0:
            consumer:
              frameMaxHeadroom: 30000
          processPayment-in-0:
            consumer:
              republishToDlq: true
              autoBindDlq: true
```

In this example, Rabbit bindings default to `frameMaxHeadroom` of 24,000 bytes. Binding `processOrder-in-0` overrides it to 30,000 bytes. Binding-specific properties take precedence over the corresponding default.

Avoid setting the largest possible value across all bindings. Each flow has different business headers, exception depths, and diagnostic needs. Choose values based on actual header sizes and environment frame limits.

## 6. Relationship Between frameMaxHeadroom and republishToDlq

The two properties address two different responsibilities:

| Property | Responsibility |
| --- | --- |
| `republishToDlq` | Chooses how the binder sends failed messages to the DLQ; when enabled, the binder adds error metadata like exception message and stack trace |
| `frameMaxHeadroom` | Reserves space for other headers when capping the stack trace added to a DLQ message |

Example configuration with retry and republish:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processPayment-in-0:
          destination: payments.requested
          group: payment-service
          consumer:
            maxAttempts: 4
            backOffInitialInterval: 1000
            backOffMaxInterval: 8000
            backOffMultiplier: 2.0
      rabbit:
        bindings:
          processPayment-in-0:
            consumer:
              autoBindDlq: true
              republishToDlq: true
              frameMaxHeadroom: 24000
```

After all four attempts within a delivery fail, the binder republishes the message to the DLQ per configuration. `frameMaxHeadroom` affects the stack trace attached during that republish step; it does not alter the retry count or decide whether the message is sent to the DLQ.

If `maxAttempts` is `1`, internal retry is disabled. Understand `requeueRejected` in that case: enabling requeue without republishing to the DLQ can cause messages to be redelivered repeatedly. Choose reject, requeue, and DLQ policies consistently to prevent unbounded loops.

## 7. What Gets Truncated When the Limit Is Exceeded?

When the stack trace exceeds the budget, the binder truncates the stack trace added to headers and logs a warning. This does not mean the message's business payload is truncated by the same mechanism. The original message is still republished with its body intact, while the stack trace in the header may only be partial.

That creates two operational requirements:

- Do not depend on the stack trace header as the sole record of failure evidence.
- Use centralized logging or an observability platform to capture complete exceptions, correlation IDs, and event IDs.

If the stack trace is truncated, the `x-exception-message` header can still help identify the error category, yet you should also inspect the size and contents of other headers. `frameMaxHeadroom` reserves room for them; it cannot make oversized headers valid if total headers exceed the frame limit.

## 8. Consumer Function Example with Concise Exceptions

A consumer can write the full exception to centralized logs and then throw a more concise business exception so the binder attaches a shorter stack trace to DLQ headers.

```java
import java.util.function.Consumer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public record OrderCreated(String eventId, String orderId) {}

@Configuration
public class OrderConsumerConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(OrderConsumerConfiguration.class);

    @Bean
    public Consumer<OrderCreated> processOrder(OrderService orderService) {
        return event -> {
            try {
                orderService.process(event);
            }
            catch (RemoteDependencyException ex) {
                // Record full cause and stack trace in centralized logging.
                log.error("Order processing failed; eventId={}, orderId={}",
                        event.eventId(), event.orderId(), ex);

                // Concise exception with lookup code, without re-attaching large cause.
                throw new OrderProcessingException(
                        "ORDER_DEPENDENCY_FAILURE eventId=" + event.eventId());
            }
        };
    }
}
```

The example assumes `RemoteDependencyException`, `OrderService`, and `OrderProcessingException` are application types. Omitting the nested cause from the new exception shortens the republished stack trace while the full exception is preserved in controlled logs. Use this approach only when correlation/event IDs let you locate full logs; never lose essential diagnostic information.

Do not shrink stack traces by arbitrarily stripping all causes or hiding root errors. Balance header limits against investigability, and avoid embedding sensitive payloads or tokens inside exception messages.

## 9. When Should frameMaxHeadroom Be Changed?

Keep the default 20,000 bytes when stack traces and business headers are normal in size. Only change it after observing truncation warnings or measuring actual header sizes.

| Scenario | Recommended approach |
| --- | --- |
| Stack trace truncated, business headers small, `frame_max` has room | Increase `frame_max` on RabbitMQ if infrastructure policy permits, or shorten the stack trace |
| Application carries many large business headers | Increase `frameMaxHeadroom` to reserve more room for those headers; accept that the retained stack trace will be shorter |
| Exception has a very long cause chain | Log full exception centrally, throw a concise exception with event ID/correlation ID |
| Large message body | Evaluate payload size and body transport; `frameMaxHeadroom` does not cap body size |
| Only one binding has large stack traces | Adjust `frameMaxHeadroom` on that specific binding instead of changing the app-wide default |
| Stack trace in DLQ not needed | Consider `republishToDlq: false` and broker dead-letter routing, after evaluating loss of binder-added exception metadata |

**Direction reminder:** increasing `frameMaxHeadroom` allocates more room to other headers and shrinks the space available for the stack trace. If the goal is preserving longer stack traces, consider raising `frame_max` or trimming stack traces rather than mechanically increasing headroom.

## 10. Where Is frame_max Managed?

`frame_max` is an AMQP protocol limit negotiated on the RabbitMQ connection. It belongs to connection/broker configuration, distinct from `frameMaxHeadroom`, which is a Rabbit binder property.

Example broker configuration setting a frame limit in `rabbitmq.conf`:

```ini
frame_max = 262144
```

The value above is only an example. Before changing it, verify limits supported by your RabbitMQ version, client library, and operational policy; existing connections may need to reconnect to renegotiate the parameter. Do not raise `frame_max` solely to mask an abnormal stack trace without investigating why it grew so large.

The two configuration layers have different scopes:

| Setting | Where configured | Effect |
| --- | --- | --- |
| `frame_max` | RabbitMQ broker/AMQP connection | Negotiated frame limit for the connection |
| `frameMaxHeadroom` | `spring.cloud.stream.rabbit.bindings.<binding>.consumer` or `spring.cloud.stream.rabbit.default` | Caps the stack trace portion the binder adds to DLQ headers, reserving space for other headers |

When raising `frame_max`, assess memory, frame size, network behavior, and client limits. Clients can propose their own frame size; the effective value is the negotiated minimum, not merely a single line in the broker config file.

## 11. Diagnosing Stack Trace Truncation Warnings

When you see a Rabbit binder warning indicating a stack trace was truncated, check in order:

1. Identify which input binding uses `republishToDlq`.
2. Confirm the effective `frameMaxHeadroom` from binding config or defaults.
3. Check the effective `frame_max` of the RabbitMQ connection.
4. Measure the size of business headers and generated stack traces.
5. Inspect whether exceptions have long cause chains, oversized messages, or sensitive data.
6. Verify centralized logs capture the full stack trace and event ID.
7. Pick the minimal fix: concise exceptions, trimming unnecessary headers, tuning headroom for business headers, or raising the frame limit if approved.
8. Recreate connections if broker/client changes require renegotiating frames.
9. Test actual republishing and confirm the DLQ still receives messages with necessary metadata.

Do not blindly increase `frame_max` or lower `frameMaxHeadroom` without measuring. If business headers already approach the limit, shrinking headroom can cause republishing to fail or starve other headers.

## 12. Testing Configuration and DLQ Behavior

Include integration tests against a real RabbitMQ broker or Testcontainers RabbitMQ for these cases:

- Consumer succeeds: message is acknowledged and does not appear in the DLQ.
- Consumer fails through `maxAttempts`: message moves to the DLQ.
- `republishToDlq: true`: DLQ message carries expected error metadata.
- Short stack trace: header retains the full expected content.
- Long stack trace: binder logs a warning and truncates the stack trace per limit; original payload remains readable.
- Large business headers: verify headroom leaves enough room for other headers.
- Binding-specific `frameMaxHeadroom` overrides the default.
- Broker `frame_max` changed: verify new connections negotiate the expected value.
- `republishToDlq: false`: verify broker dead-letter routing and absence of binder-republished stack traces.
- DLQ publish failure: verify acknowledgements/transactions and ensure messages are not silently lost.

Unit tests can verify concise exception selection or header mapping, but cannot prove frame negotiation and AMQP frame sizing. Those behaviors require integration tests with RabbitMQ and your real binder version.

## 13. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| `frameMaxHeadroom` increases RabbitMQ's frame limit | It only reserves space for other headers when the binder caps stack traces; `frame_max` is still governed by broker/connection |
| Increasing `frameMaxHeadroom` preserves longer stack traces | Increasing headroom allocates more space to other headers, so the stack trace budget shrinks |
| A truncated stack trace means the payload was lost | This property targets stack traces in error headers, not the payload body |
| `frameMaxHeadroom` is a producer property | It is a Rabbit binder consumer property used when republishing errors to a DLQ |
| Enabling `autoBindDlq` automatically adds stack traces | `autoBindDlq` declares the DLQ/DLX; `republishToDlq` controls republishing with error metadata |
| Putting the property under `spring.cloud.stream.bindings` is enough | Must use the Rabbit-specific namespace `spring.cloud.stream.rabbit.bindings...consumer` or `spring.cloud.stream.rabbit.default` |

## 14. Production Checklist

Before deploying a Rabbit consumer with DLQ republishing:

- Set a stable consumer group and identify the target DLQ/DLX.
- Explicitly configure `autoBindDlq` or pre-provisioned DLQ infrastructure.
- Decide whether `republishToDlq` and stack trace metadata are needed.
- Set retry count/backoff appropriate to the error profile.
- Confirm effective `frame_max` and per-binding `frameMaxHeadroom`.
- Measure business headers and stack trace lengths under realistic error cases.
- Record full exceptions in centralized logs with event ID/correlation ID.
- Ensure exception messages never contain sensitive payloads or oversized data.
- Monitor stack trace truncation warnings and DLQ publish failures.
- Test small headers, large headers, long stack traces, and broker reconnects.
- Verify the DLQ preserves payloads, keys, delivery mode, and required metadata.
- Document broker and binder settings in operational runbooks.

## References

- [Spring Cloud Stream RabbitMQ Binder — Consumer Properties (`frameMaxHeadroom`, `republishToDlq`)](https://docs.spring.io/spring-cloud-stream-binder-rabbit/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html)
- [Spring Cloud Stream RabbitMQ Binder — DLQ behavior](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
- [RabbitMQ — AMQP 0-9-1 Protocol and Frame](https://www.rabbitmq.com/amqp-0-9-1-reference)
- [RabbitMQ — Configuration](https://www.rabbitmq.com/docs/configure)

Cross-check documentation against the exact versions of Spring Cloud Stream Rabbit binder, Spring AMQP, and RabbitMQ deployed. In particular, verify the `frameMaxHeadroom` default, `republishToDlq` setting, headers preserved by mappers, and effective connection frame limits.

## Conclusion

When the Rabbit binder republishes a failed message to a DLQ, the stack trace attached to headers can exceed `frame_max`. `frameMaxHeadroom` reserves bytes for other headers; its default is 20,000 bytes. If the stack trace plus reserved headroom exceeds the limit, the binder truncates the stack trace and logs a warning. This property does not change `frame_max` and does not limit the payload body. To keep useful error details, configure it on the right Rabbit consumer binding, measure header sizes, store full exceptions in centralized logs, and only adjust broker frame limits or stack traces after assessing impact.