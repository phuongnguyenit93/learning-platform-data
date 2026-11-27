# Applying ChannelInterceptor and GlobalChannelInterceptor to the Right Binding

## Objectives

In a Spring Cloud Stream application, multiple message flows may share a binder while requiring different rules: adding a correlation ID to order events, validating partner message headers, counting throughput of a payment stream, or recording channel send times. Putting all of that logic inside every `Supplier`, `Function`, or `Consumer` leads to duplicated business code and makes scoping hard to control.

Spring Messaging provides `ChannelInterceptor` to intercept send/receive operations on a `MessageChannel`. Spring Integration provides `@GlobalChannelInterceptor` to register an interceptor for **channels whose names match a pattern**. Spring Cloud Stream uses message channels in its standard binder model, including output bindings created by `StreamBridge`. Thus, interceptors help implement cross-cutting rules, though a misconfigured pattern can apply the rule to too many bindings or prevent it from running at all.

This lesson in the **Scaling** chapter of the **SPRING_CLOUD_STREAM** module guides you on scoping interceptors to the right bindings when building event-driven systems with `Supplier`, `Function`, `Consumer`, Kafka, RabbitMQ, and Pulsar. It focuses on differences among channel, binding, and destination; selective global configuration; interaction with `StreamBridge`; callback ordering; testing with the test binder; and limitations when using the Kafka Streams DSL.

After this lesson, you will be able to:

- Distinguish `MessageChannel`, binding name, broker destination, and consumer group.
- Explain the `preSend`, `postSend`, and `afterSendCompletion` lifecycle.
- Register an interceptor for a specific channel or by pattern.
- Use `@GlobalChannelInterceptor(patterns = "...")` to target the right bindings.
- Understand why `StreamBridge` requires interceptors registered via the global mechanism.
- Tune `order` when multiple interceptors apply together.
- Avoid accidentally swallowing messages or running long side effects.
- Distinguish channel interception from Kafka/Pulsar/RabbitMQ client interceptors or the Kafka Streams DSL.
- Test both cases where an interceptor must run and where it must be excluded.
- Observe header modifications, errors, and overhead as the system scales.

## 1. Channel, Binding, and Destination Are Three Different Concepts

In Spring Cloud Stream, a binding connects application logic to a destination on the middleware. Under the functional model, default binding names follow this convention:

- `<functionName>-in-0` for input.
- `<functionName>-out-0` for output.
- Indices `0`, `1`, ... for functions with multiple inputs/outputs.

Example:

~~~java
@Bean
Function<OrderCreated, OrderAccepted> validateOrders() {
    return event -> new OrderAccepted(event.orderId(), "ACCEPTED");
}
~~~

Configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrders
    stream:
      bindings:
        validateOrders-in-0:
          destination: orders.created
          group: order-validation
        validateOrders-out-0:
          destination: orders.accepted
~~~

There are four identifiers to remember:

| Concept | Example | Meaning |
|---|---|---|
| Function bean | `validateOrders` | Executes business logic |
| Binding name | `validateOrders-in-0` | Connects logic to the binder |
| Broker destination | `orders.created` | Kafka topic, RabbitMQ exchange/queue, or Pulsar topic |
| Consumer group | `order-validation` | Consumer/subscription group per binder semantics |

`@GlobalChannelInterceptor` matches against the **Spring Integration message channel name**, not the topic name, RabbitMQ queue name, Kafka consumer group, or Java class name. In the message-channel binder model, binding-related channels are typically named after the binding name; the application should verify actual names when using aliases, function composition, or dynamic bindings.

For example, `patterns = "orders.created"` will not automatically match channel `validateOrders-in-0` just because the binding's destination is `orders.created`.

### High-Level Processing Flow

~~~mermaid
flowchart LR
    T[(Topic / Queue)] --> B[Binder input adapter]
    B --> IC[Input MessageChannel]
    IC --> F[Function bean]
    F --> OC[Output MessageChannel]
    OC --> P[Binder output adapter]
    P --> D[(Destination)]
~~~

An interceptor attached to `IC` or `OC` operates on message sends through that channel. It does not sit independently at the broker and does not automatically monitor every Kafka, RabbitMQ, or Pulsar operation outside this channel.

## 2. What Does ChannelInterceptor Do?

`org.springframework.messaging.support.ChannelInterceptor` is a Spring Messaging interface. It provides callbacks around `MessageChannel.send(...)` and, for pollable channels, around `receive(...)`.

| Callback | Timing | Key notes |
|---|---|---|
| `preSend` | Before the message is sent to the channel | Can create a new message or return `null` to block the send |
| `postSend` | After the send call | Receives the `sent` boolean of the send operation |
| `afterSendCompletion` | When the send operation finishes, including exceptions | Resource cleanup; applies only if `preSend` returned a valid message |
| `preReceive` | Before the receive call | Only for `PollableChannel` |
| `postReceive` | After receive returns a message | Only for `PollableChannel` |
| `afterReceiveCompletion` | After receive completes | Cleans up resources related to receive |

In regular function bindings, `preSend` is the callback commonly used to add headers, inspect metadata, or count messages passing through the channel. `postSend` and `afterSendCompletion` are suitable for recording channel-operation success/failure, not business-level broker confirmation.

### Example Header-Observing Interceptor

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;

public final class CorrelationObserver implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {
        Object correlationId =
                message.getHeaders().get("x-correlation-id");

        if (correlationId == null) {
            // Record missing-header metric; avoid logging full payload.
        }

        return message;
    }
}
~~~

Returning `message` lets the message continue. If you only want to observe, do not modify payload or headers without an explicit requirement.

### Returning null from preSend Blocks the Message

~~~java
@Override
public Message<?> preSend(Message<?> message, MessageChannel channel) {
    if (shouldReject(message)) {
        return null;
    }
    return message;
}
~~~

Per the `ChannelInterceptor` contract, returning `null` means the send operation does not proceed. This can drop messages without going through a DLQ in the way you might expect. For business data requiring at-least-once delivery, do not use `return null` as a default error-handling mechanism. Check binder outcomes, error handling, and acknowledgment in integration tests; consider a filter/router or a broker-appropriate reject/dead-letter mechanism.

## 3. Distinguishing Local and Global Interceptors

There are two main registration approaches:

1. Attach a `ChannelInterceptor` directly to an `InterceptableChannel` managed by the application.
2. Declare a `ChannelInterceptor` bean with `@GlobalChannelInterceptor` so Spring Integration finds channels matching the pattern and attaches the interceptor.

Comparison:

| Aspect | Local registration | Global with pattern |
|---|---|---|
| Scope | One known channel | Channels whose names match the pattern |
| Configuration | `channel.addInterceptor(...)` | `@GlobalChannelInterceptor(patterns = "...")` |
| Framework-created channels | Must obtain the exact channel instance and lifecycle | Usually easier to control by binding name |
| With `StreamBridge` | Difficult if channels are created dynamically | Recommended approach in Spring Cloud Stream docs |
| Risk | Attaching to the wrong instance | Pattern too broad or fails to match |

Do not simply create a bean implementing `ChannelInterceptor` and expect `StreamBridge` to add it to all output bindings automatically. Spring Cloud Stream relies on `@GlobalChannelInterceptor` to select interceptors.

## 4. Local Registration When Owning the MessageChannel

When the application creates a Spring Integration channel itself, it can attach the interceptor at declaration time:

~~~java
@Configuration(proxyBeanMethods = false)
class InternalChannelConfig {

    @Bean
    DirectChannel internalAuditChannel() {
        DirectChannel channel = new DirectChannel();
        channel.addInterceptor(new CorrelationObserver());
        return channel;
    }
}
~~~

`DirectChannel` is an `InterceptableChannel`; `addInterceptor(...)` appends the interceptor to that channel's list.

This works well for internal channels managed by the application. For channels created by Spring Cloud Stream for function bindings, do not manually declare a new `DirectChannel` with the same name assuming the binder will use that instance. If you must interact with a framework-generated channel, verify the actual bean/channel and initialization order in your release; in most cases, a global interceptor pattern is clearer.

### Do Not Mistake a Plain ChannelInterceptor Bean for a Binding

The following example only creates a bean:

~~~java
@Bean
ChannelInterceptor auditInterceptor() {
    return new CorrelationObserver();
}
~~~

It does not express which channel should use the interceptor. For `StreamBridge`, if you need to select bindings by name, declare `@GlobalChannelInterceptor(patterns = "...")`.

## 5. Applying @GlobalChannelInterceptor to One Output Binding

Suppose a system has two outputs:

- `orders-out-0` emits order events.
- `audit-out-0` emits audit events.

Requirement: add header `x-source-binding` only to messages on `orders-out-0`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.GlobalChannelInterceptor;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageBuilder;

@Configuration(proxyBeanMethods = false)
class InterceptorConfiguration {

    @Bean
    @GlobalChannelInterceptor(patterns = "orders-out-0")
    ChannelInterceptor ordersOutputMetadata() {
        return new ChannelInterceptor() {

            @Override
            public Message<?> preSend(
                    Message<?> message,
                    MessageChannel channel) {
                return MessageBuilder.fromMessage(message)
                        .setHeaderIfAbsent(
                                "x-source-binding", "orders-out-0")
                        .build();
            }
        };
    }
}
~~~

Key points:

- The pattern matches the **channel/binding name** `orders-out-0`.
- `setHeaderIfAbsent` preserves an existing header value; if a trusted source must be enforced, define a dedicated overwrite/validation policy.
- `MessageBuilder.fromMessage(...)` constructs a new message, copying payload and headers per the API without mutating the original message.
- `audit-out-0` does not match, so this interceptor is not attached to that channel.
- If the actual binding name is remapped, the pattern must match the effective channel name.

An interceptor can attach to unintended channels if a pattern matches too broadly; pick a tight pattern and write tests covering the "must not apply" direction as well.

## 6. Applying to an Input Binding

An interceptor can also be declared for an input channel of a regular message-channel binder:

~~~java
@Bean
@GlobalChannelInterceptor(patterns = "validateOrders-in-0", order = -10)
ChannelInterceptor inboundCorrelationCheck() {
    return new ChannelInterceptor() {
        @Override
        public Message<?> preSend(
                Message<?> message,
                MessageChannel channel) {

            Object id = message.getHeaders().get("x-correlation-id");

            if (!(id instanceof String value) || value.isBlank()) {
                throw new IllegalArgumentException(
                        "Missing x-correlation-id");
            }

            return message;
        }
    };
}
~~~

This example illustrates scoping an interceptor to the specified input binding. Throwing an exception in `preSend` raises the error **before the business function executes**, and how the binder handles it (retry, ack/nack, error channel, DLQ) depends on the implementation. In production, test the failure path against a real broker before using an interceptor to reject messages.

Do not assume the interceptor always sees a deserialized POJO matching the function parameter. When payload/header conversion happens depends on the integration flow, binder, and content type. When only checking a correlation ID, operate on metadata independent of the payload class.

## 7. Global Interceptor for All Bindings

Spring Cloud Stream recommends `@GlobalChannelInterceptor(patterns = "*")` when an interceptor should apply broadly across message channels, including eligible `StreamBridge` outputs.

~~~java
@Bean
@GlobalChannelInterceptor(patterns = "*", order = 20)
ChannelInterceptor globalMetricsInterceptor(MeterRegistry registry) {
    return new ChannelInterceptor() {
        @Override
        public Message<?> preSend(
                Message<?> message,
                MessageChannel channel) {
            registry.counter("stream.channel.sends").increment();
            return message;
        }
    };
}
~~~

The `*` pattern has a very broad scope. It can touch integration flow channels, error paths, or other internal channels depending on the Spring context. If you only need to measure a service's outputs, use `*-out-0` or an explicit name list and verify which channels are actually matched.

### Do Not Use Wildcards for Side-Effect Logic

Global interceptors fit lightweight, safe operations such as metrics or neutral metadata enrichment. Avoid:

- Synchronous remote service calls on every message.
- Executing payments, sending emails, or updating databases inside `preSend`.
- Logging entire payloads that may contain sensitive data.
- Using `return null` as a default filter.
- Applying one topic's specialized validation policy to every channel.

An interceptor on the hot path executes once per message across all matching channels. Even a few milliseconds of overhead per message can sharply reduce throughput under heavy load.

## 8. Applying Multiple Patterns and Excluding Channels

`@GlobalChannelInterceptor` accepts one or more patterns:

~~~java
@Bean
@GlobalChannelInterceptor(
        patterns = {"orders-out-0", "returns-out-0"},
        order = 5)
ChannelInterceptor businessEventHeaders() {
    return new ChannelInterceptor() {
        @Override
        public Message<?> preSend(
                Message<?> message,
                MessageChannel channel) {
            return MessageBuilder.fromMessage(message)
                    .setHeaderIfAbsent("x-event-source", "commerce")
                    .build();
        }
    };
}
~~~

In modern Spring Integration, patterns support wildcards and negated patterns prefixed with `!`. For example:

~~~java
@GlobalChannelInterceptor(
        patterns = {"orders-*", "!orders-debug*"})
~~~

This configuration illustrates matching the `orders-` group while excluding debug channels using Spring Integration's pattern matcher rules. Test both positive and negative patterns; do not merely verify the annotation is present.

| Pattern | Intent | Risk |
|---|---|---|
| `orders-out-0` | One output binding | Stops matching if the binding is renamed |
| `orders-*` | Channels in the orders group | Can match input/error/internal channels sharing the prefix |
| `*-out-0` | Multiple output channels | Does not guarantee every match is only an output binding |
| `*` | All eligible channels | Very wide scope |
| `orders-*`, `!orders-debug*` | Include orders, exclude debug | Depends on version's pattern matcher semantics |

Patterns are evaluated against channel names. `patterns = "payments.*"` does not automatically filter messages by event type, header, payload class, or topic routing. To route messages by content, use a router/filter at the appropriate layer.

## 9. Binding Aliases and Effective Channel Names

Spring Cloud Stream allows mapping default binding names to more descriptive ones:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrders
    stream:
      function:
        bindings:
          validateOrders-in-0: orderInput
          validateOrders-out-0: orderOutput
      bindings:
        orderInput:
          destination: orders.created
          group: order-validation
        orderOutput:
          destination: orders.accepted
~~~

With this remapping, binding configuration uses `orderInput` and `orderOutput`. When selecting an interceptor pattern, verify the channel bean names actually registered by the binder in the application context and use the matching names, instead of copying `validateOrders-in-0` from another example.

### How to Avoid Name Mix-ups

1. List effective bindings at startup and via `/actuator/bindings` if the endpoint is enabled.
2. Inspect `MessageChannel` bean names in the Spring context when diagnosing.
3. Check function definitions, `spring.cloud.stream.function.bindings` remappings, and dynamic binding names.
4. Pick patterns matching observed channel names.
5. Write integration tests asserting the interceptor runs on the intended binding and does not run on others.

The `bindings` endpoint reflects binding lifecycles; it does not necessarily list all internal channels. When proving a pattern match, inspect the channel/interceptor list or test actual behavior rather than checking only the broker destination.

## 10. StreamBridge and Dynamically Created Channels

`StreamBridge` lets imperative flows—such as REST requests, scheduled jobs, or external callbacks—send messages to output bindings without a fixed `Supplier`.

~~~java
@Service
class EventPublisher {

    private final StreamBridge bridge;

    EventPublisher(StreamBridge bridge) {
        this.bridge = bridge;
    }

    boolean sendOrder(OrderCreated event) {
        return bridge.send("orders-out-0", event);
    }

    boolean sendAudit(String event) {
        return bridge.send("audit-out-0", event);
    }
}
~~~

The first send can dynamically create the output binding/channel. Spring Cloud Stream documentation states clearly that `StreamBridge` uses `MessageChannel` and interceptors must be declared via `@GlobalChannelInterceptor`. Two options illustrated by the docs:

- `@GlobalChannelInterceptor(patterns = "*")`: applies broadly to `StreamBridge` outputs.
- `@GlobalChannelInterceptor(patterns = "orders-*")`: applies only to output channels with matching names.

Do not assume standalone `ChannelInterceptor` beans will be automatically added to `StreamBridge`'s interceptor chain. Likewise, you do not need to declare channel beans manually just for `StreamBridge` to see an interceptor; use an explicit global pattern.

### Dynamic Outputs Require Testing the First Send

An easily missed detail is that the channel may not exist yet right when the application context finishes starting. Modern Spring Integration supports global interceptors for dynamically registered channels. However, how `StreamBridge` creates bindings and names channels can depend on version; test both the first send and subsequent sends on your exact Spring Cloud Stream release.

In applications with a large set of dynamic destinations, also watch the dynamic binding cache limit. An interceptor operates on channels; it does not validate destinations or grant topic-creation permissions.

## 11. Interceptor Ordering Across Multiple Layers

When multiple interceptors match the same channel, their order determines what data each interceptor observes or mutates.

Example:

- Interceptor A adds `x-correlation-id`.
- Interceptor B validates `x-correlation-id`.
- Interceptor C records metrics.

If B runs before A, B may reject the message because the header has not been added yet.

`@GlobalChannelInterceptor` provides an `order` attribute:

~~~java
@Bean
@GlobalChannelInterceptor(patterns = "orders-out-0", order = -20)
ChannelInterceptor correlationEnricher() {
    return new CorrelationEnricher();
}

@Bean
@GlobalChannelInterceptor(patterns = "orders-out-0", order = 20)
ChannelInterceptor correlationValidator() {
    return new CorrelationValidator();
}
~~~

Per Spring Integration, a negative `order` places a global interceptor before local interceptors configured on the channel; a positive `order` places it after local interceptors. Multiple global interceptors matching the same channel are sorted by their order values. The default value is `0`.

However, the full interceptor chain order also depends on how the channel is built and any internal framework interceptors. If logic depends strictly on order, inspect `getInterceptors()` on the actual channel and write test cases verifying transformations on input data.

### Completion Callbacks Have Their Own Order

`afterSendCompletion` is called when `send` ends, including on exceptions; cleanup order is normally the reverse of pre-send order for participating interceptors. Do not treat `postSend` as final broker ack. To know whether a Kafka send was acknowledged by the broker or a RabbitMQ publish was confirmed, use the corresponding producer/binder callbacks or confirms.

## 12. Mutating Headers Safely

Headers are metadata that can traverse multiple services. Changing headers in an interceptor can alter routing, tracing, and security behavior.

Example adding a correlation ID if absent:

~~~java
@Bean
@GlobalChannelInterceptor(patterns = "orders-out-0")
ChannelInterceptor correlationIdInterceptor() {
    return new ChannelInterceptor() {
        @Override
        public Message<?> preSend(
                Message<?> message,
                MessageChannel channel) {

            Object existing =
                    message.getHeaders().get("x-correlation-id");

            if (existing instanceof String id && !id.isBlank()) {
                return message;
            }

            return MessageBuilder.fromMessage(message)
                    .setHeader(
                            "x-correlation-id",
                            UUID.randomUUID().toString()
                    )
                    .build();
        }
    };
}
~~~

The intent is to populate an ID only when no valid one exists. However, in flows requiring a stable correlation ID across an event chain, generating a new ID on every retry or every service can break traceability. It is better to generate the ID at the trust boundary and preserve it per contract.

Key guidelines:

- Use `MessageBuilder.fromMessage` to build a new message.
- Do not replace the payload unless content type and target type are explicitly defined.
- Do not assume every header is forwarded by the broker mapper.
- Do not write credentials, PII, or sensitive data into logs or metric labels.
- Do not trust arbitrary producer-supplied tenant/role headers for authorization decisions.
- Bound header size, charset, and types to prevent unexpected serialization overhead.

## 13. Observing via postSend and afterSendCompletion

You can measure how often a channel receives send requests:

~~~java
@Bean
@GlobalChannelInterceptor(patterns = "orders-out-0")
ChannelInterceptor channelMetrics(MeterRegistry registry) {
    return new ChannelInterceptor() {
        @Override
        public Message<?> preSend(
                Message<?> message,
                MessageChannel channel) {
            registry.counter(
                    "orders.channel.pre_send"
            ).increment();
            return message;
        }

        @Override
        public void postSend(
                Message<?> message,
                MessageChannel channel,
                boolean sent) {
            registry.counter(
                    "orders.channel.post_send",
                    "sent", Boolean.toString(sent)
            ).increment();
        }

        @Override
        public void afterSendCompletion(
                Message<?> message,
                MessageChannel channel,
                boolean sent,
                Exception ex) {
            if (ex != null) {
                registry.counter(
                        "orders.channel.errors"
                ).increment();
            }
        }
    };
}
~~~

These are metrics of the **channel send** operation. `sent = true` does not mean the Kafka broker committed the record, a RabbitMQ publisher confirm arrived, or a Pulsar producer received durable acknowledgment. The producer may still send asynchronously after this callback.

At high throughput, metrics must use bounded-cardinality tags: binding name or send status, avoiding event ID, order ID, or correlation ID as tags.

### Measuring Latency at the Right Stage

If you need to measure business processing time or broker acknowledgment latency, instrument the appropriate API in the function, producer callback, or Micrometer Observation. Duration from `preSend` to `afterSendCompletion` reflects only the channel operation scope; with asynchronous channels, it can finish before the business handler completes.

## 14. Limitations by Binder Type and Programming Model

Not every binder defines the same internal `MessageChannel` for data flow.

| Model | Primary data path | Should you use ChannelInterceptor? |
|---|---|---|
| Regular Kafka binder with `Function<T,R>` | Spring MessageChannel + Kafka adapter | Yes, on matching binding channels |
| RabbitMQ binder with imperative function | Spring MessageChannel + AMQP adapter | Yes, on matching binding channels |
| Pulsar binder with message-channel function | Depends on binder/version adapter | Verify channel interception in integration tests |
| `StreamBridge` output | Created/sent via MessageChannel | Yes, when registered as a global interceptor by pattern |
| Kafka Streams binder `KStream/KTable` | Kafka Streams DSL/topology | Do not assume `ChannelInterceptor` intercepts every record |
| Direct Kafka client outside the binder | Kafka client API | Needs Kafka producer/consumer interceptors or custom instrumentation |

The Kafka Streams binder uses `KStream`, `KTable`, Kafka Streams Serdes, and processor topologies. Spring Messaging's `ChannelInterceptor` is not a Kafka Streams `Processor`. If you need to process headers or emit per-record metrics inside a topology, use the Kafka Streams DSL/Processor API or Kafka Streams metrics as appropriate.

Similarly, Kafka's `ProducerInterceptor`/`ConsumerInterceptor` are Kafka client interfaces with a different scope from `ChannelInterceptor`. Do not register one and claim to intercept every stage of the other.

## 15. Interceptors and Consumer Groups/Partitions

Interceptors do not increase throughput or partition counts on their own. When scaling out to multiple replicas, each replica runs its own interceptor chain on the channels created within that process.

Example:

- Three replicas read from group `order-validation`.
- Each replica registers the interceptor for `validateOrders-in-0`.
- Messages are distributed per binder/consumer-group semantics.
- The interceptor runs only on the replica that actually receives the message through that channel.

Therefore, do not multiply a local interceptor metric by the replica count without considering load distribution. Raising concurrency or partitions increases the number of threads invoking the interceptor; the interceptor must be thread-safe.

Do not store mutable per-message state in unsynchronized shared interceptor fields. For instance, a plain `HashMap` is unsafe across multiple consumer threads. Use a metrics registry, immutable configuration, or proper concurrency primitives; store keyed event state in a state store or broker if durability across restarts is needed.

## 16. Thread Safety and Interceptor Cost

A single interceptor bean can be invoked concurrently by multiple channels or multiple consumer threads. Operations in `preSend` should:

- Execute quickly without long blocking I/O.
- Not retain references to large payloads after the callback.
- Not spawn a new thread per message.
- Not acquire coarse `synchronized` locks on every send.
- Not query databases on the hot path unless genuinely required.
- Avoid logging payloads; prefer message counts, elapsed time, and error classes.
- Use safe message builders when adding headers.
- Handle null, wrongly typed, or invalid header values gracefully.

A global interceptor runs at a frequency equal to total messages across all matching channels. For example, four bindings each handling 1,500 messages/second produce around 6,000 `preSend` calls per second. If each callback takes 2 ms of CPU on average, theoretical CPU load is roughly 12 CPU-seconds per wall-clock second at that scale; thus even small logic deserves benchmarking.

### Avoid Creating Message-Publishing Loops

If an interceptor emits audit events via `StreamBridge`, the audit output may also match the global pattern and trigger the interceptor again, causing recursion or message storms.

Conceptually flawed example:

~~~java
@GlobalChannelInterceptor(patterns = "*")
ChannelInterceptor auditEveryMessage(StreamBridge bridge) {
    return new ChannelInterceptor() {
        @Override
        public Message<?> preSend(
                Message<?> message,
                MessageChannel channel) {
            bridge.send("audit-out-0", "message seen");
            return message;
        }
    };
}
~~~

Do not do this. For auditing, exclude the audit channel in the pattern, integrate observation without synchronously publishing back into the same chain, or use a dedicated outbox/audit flow.

## 17. Testing the Right Binding with StreamBridge and Test Binder

Spring Cloud Stream Test Binder provides `InputDestination`/`OutputDestination` for in-JVM wiring tests. For `StreamBridge`, tests should prove both sides: the target binding receives the new header, while other bindings remain untouched.

Test dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
</dependency>
~~~

Illustrative integration test:

~~~java
@SpringBootTest(properties = {
        "spring.cloud.stream.output-bindings=orders-out-0;audit-out-0"
})
@EnableTestBinder
class ScopedInterceptorTest {

    @Autowired
    StreamBridge bridge;

    @Autowired
    OutputDestination output;

    @Test
    void appliesOnlyToOrdersOutput() {
        bridge.send("orders-out-0", "order-event");
        bridge.send("audit-out-0", "audit-event");

        Message<byte[]> orders =
                output.receive(2_000, "orders-out-0");
        Message<byte[]> audit =
                output.receive(2_000, "audit-out-0");

        assertThat(orders).isNotNull();
        assertThat(audit).isNotNull();

        assertThat(
                orders.getHeaders().get("x-source-binding"))
                .isEqualTo("orders-out-0");

        assertThat(
                audit.getHeaders().get("x-source-binding"))
                .isNull();
    }
}
~~~

This test needs to import `InterceptorConfiguration` from section 5. Configuring `spring.cloud.stream.output-bindings` declares output bindings explicitly for testing; for pure dynamic creation, you can omit that property and assert on the very first `StreamBridge.send`.

When testing, note:

- Test Binder requires no Kafka/Rabbit/Pulsar broker.
- Pass the actual output binding name to `OutputDestination.receive(...)`.
- Keep timeouts finite.
- If the same test context hosts multiple functions/bindings, configure output names explicitly.
- Do not infer that headers will survive real broker mapping solely because an in-memory test passed.
- Test non-matching bindings and negative patterns when applicable.

### Verifying Interceptor Invocation Counts

Use a thread-safe counter (e.g., `AtomicInteger`) or spy bean to verify:

- One message on `orders-out-0` triggers the interceptor once.
- A message on `audit-out-0` does not trigger it.
- The first dynamic `StreamBridge` send also applies it.
- Across repeated sends, the interceptor is not registered multiple times.
- When `order` matters, interceptors run in the exact expected sequence.

Do not assert that callback count equals business event count if a single message traverses multiple channels matching the pattern. Total `preSend` calls across distinct channels can exceed published event count.

## 18. Broker Integration Testing for Header Mapping and Errors

Test Binder proves the interceptor is wired properly in the application context, but does not prove headers/payloads traverse Kafka, RabbitMQ, or Pulsar with the expected wire format.

With Kafka, RabbitMQ, or Pulsar, run tests against real middleware:

1. Send messages through `StreamBridge` or a function output.
2. Consume records on the other side with an appropriate binder/client.
3. Verify `x-source-binding` and content type pass through the header mapper.
4. Verify serializers/deserializers reconstruct the payload type properly.
5. Confirm the interceptor did not unexpectedly alter message keys, partition keys, or routing headers.
6. Force handlers/interceptors to throw exceptions and observe retry/ack/DLQ behavior.
7. Resend the same message after a restart and verify idempotency.
8. Increase concurrency to surface race conditions.
9. Measure throughput/latency with the interceptor enabled vs. disabled.

With the Kafka Streams binder, test with dedicated Kafka Streams topology/integration tests rather than relying on `ChannelInterceptor` to verify per-record interception.

### Interceptor Failure Does Not Default to DLQ

If `preSend` throws an exception, `MessageChannel.send` can fail before reaching the function or broker. Whether retry/nack/DLQ happens is determined by the binder's error path. A single callback alone does not define delivery guarantees.

Do not swallow exceptions and return a valid message when required work has failed. If data validation is needed, consider placing it inside the function where contracts and error policies are easier to test.

## 19. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| Interceptor bean exists but `StreamBridge` ignores it | Missing `@GlobalChannelInterceptor` or pattern mismatch | Add the annotation and check binding/channel names |
| Pattern uses Kafka topic name and never fires | Global interceptor matches channel name, not broker destination | Use the effective channel name |
| Interceptor fires on every flow | `patterns = "*"` is too broad | Use a specific pattern or explicit binding list |
| Interceptor stops running after binding rename | Alias changed configuration/channel name | Check `function.bindings` and channel beans |
| Header present in Test Binder but missing at broker | Header mapper/binder drops it | Run broker integration tests and configure header mapping |
| Message vanishes without going to DLQ | `preSend` returned `null` | Design explicit reject/filter behavior; verify ack |
| Interceptor runs twice | Same bean registered both globally and locally, or duplicated registration | Inspect `getInterceptors()` |
| `postSend` has `sent=true` yet broker lacks the record | Channel send does not reflect broker acknowledgment | Use producer send results/confirms and broker metrics |
| Kafka Streams records bypass interceptor | `KStream` executes via Kafka Streams DSL | Use Processor API, transforms, or Kafka client interceptors |
| High CPU after adding metrics | Global interceptor blocks/logs heavily or high tag cardinality | Reduce callback cost and narrow pattern scope |
| Duplicate audit event storm | Audit interceptor triggers the audit output channel itself | Exclude audit channel or separate the flow |
| Exception triggers multiple retries | Validation sits ahead of function and binder retries | Classify errors, design retry budget and DLQ |
| Flaky test on dynamic bindings | Test misses first-send timing / lazy channel creation | Test dynamic binding creation and lifecycle explicitly |
| Thread-safety bugs under scaling | Interceptor holds unsynchronized mutable state | Use thread-safe state or keep interceptor stateless |

## 20. Workflow for Choosing Interceptors in Multi-Binding Systems

When applying a cross-cutting policy, follow this sequence:

1. List all functions, binding names, destinations, and groups in the application.
2. Identify whether each data path uses regular message channels or the Kafka Streams DSL.
3. Choose the policy: metadata enrichment, validation, metrics, or tracing.
4. Identify the exact input/output channels to target.
5. If the channel is owned by the application, consider `addInterceptor`.
6. For Spring Cloud Stream bindings, prefer `@GlobalChannelInterceptor` with specific patterns.
7. For `StreamBridge`, use the global annotation so the interceptor is picked up when output channels are created.
8. Write both "must run" and "must not run" tests.
9. Define interceptor order and test whenever ordering matters.
10. If modifying headers, verify broker header mapping and backward compatibility.
11. If the interceptor can throw exceptions, test retry/ack/DLQ on the broker.
12. Measure overhead, thread safety, and callback counts under realistic load.
13. Establish security policies for headers, logs, and metrics.
14. Document patterns and binding names in the runbook; update tests whenever functions/bindings are renamed.

### Quick Selection Rules

| Need | Preferred tool |
|---|---|
| Add header to one `StreamBridge` output | `@GlobalChannelInterceptor(patterns = "orders-out-0")` |
| Observe all message channels in the app | Global interceptor `patterns = "*"`, mindful of scope and cost |
| Intercept an internal self-created channel | `InterceptableChannel.addInterceptor` |
| Validate typed business payloads | Explicit function/validator with contract tests |
| Modify Kafka records inside a `KStream` | Kafka Streams DSL/Processor API |
| Track producer send acknowledgments | Kafka producer callbacks, Rabbit confirms, or Pulsar send acknowledgments |
| Track delivery/retry/DLQ | Binder/broker metrics and error handling |
| Trace HTTP requests before publishing | HTTP filter/interceptor or controller instrumentation |

## Conclusion

`ChannelInterceptor` intercepts send/receive operations on a `MessageChannel`; `@GlobalChannelInterceptor` binds an interceptor to channels whose names match a pattern. In Spring Cloud Stream, distinguish **binding name** from **broker destination** and **consumer group** so you do not pick the wrong scope. With `StreamBridge`, interceptors must be declared using the global mechanism supported by framework docs; use targeted patterns when only one binding or group of bindings should match.

An interceptor should be lightweight, thread-safe, and free of hard-to-roll-back business side effects. `preSend` can alter messages or block sends by returning `null`; `postSend` only reports the channel send result and does not guarantee broker acknowledgment. Do not assume `ChannelInterceptor` runs per record inside the Kafka Streams DSL.

Verify target bindings with the Test Binder, including bindings that must be excluded; then run Kafka/RabbitMQ/Pulsar integration tests to validate headers, retries, acks, and wire behavior. As you scale across instances and bindings, keep patterns precise, callbacks cheap, and interceptor state concurrency-safe.

## Official References

- [Spring Cloud Stream — Producing and Consuming Messages, Using Channel Interceptors with StreamBridge](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html): `StreamBridge` mechanism and `@GlobalChannelInterceptor(patterns = "*")` or scoped pattern examples.
- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html): function-based binding names and aliases.
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html): destination, group, and per-binding configuration.
- [Spring Integration — Global Channel Interceptor Configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html): patterns, negative patterns, order, and matched channels.
- [Spring Integration — GlobalChannelInterceptor API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/config/GlobalChannelInterceptor.html): annotation and `patterns`/`order` semantics.
- [Spring Framework — ChannelInterceptor API](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html): `preSend`, `postSend`, `afterSendCompletion` callbacks and `return null` behavior.
- [Spring Cloud Stream — Kafka Streams Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html): Kafka Streams topology configuration model differing from regular message channels.
- [Spring Cloud Stream — Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html): Test Binder and `InputDestination`/`OutputDestination`.

When implementing, verify your exact versions of Spring Cloud Stream, Spring Integration, Spring Boot, and binders. Dynamic binding channel names, alias mappings, and callback/lifecycle behavior should be verified with tests against your exact production dependency combination.
