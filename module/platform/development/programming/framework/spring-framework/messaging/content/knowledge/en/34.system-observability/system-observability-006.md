# Propagating Tracing Context Across Headers and Async Boundaries

## Objectives

After this lesson, you can:

- Explain trace, span, parent span, and baggage in distributed tracing.
- Recognize the roles of W3C standard headers such as **traceparent**, **tracestate**, and **baggage**.
- Propagate trace context via Spring Message headers and native STOMP headers.
- Use Micrometer Tracing to inject context into outgoing messages and extract context when receiving messages.
- Preserve context when work crosses executors, thread pools, or Reactor pipelines.
- Verify continuous traces across multiple services without leaking context between requests.

## 1. Why Propagate Trace Context?

A request in a messaging system often traverses many components: API gateway, command-receiving service, message broker, consumer, executor, and downstream dependencies. Each component may run on a different thread or process. With only local logging, when a message becomes slow or fails, it is very hard to stitch events back into a single processing flow.

Distributed tracing assigns a workflow a **trace ID** and breaks it into **spans**. Each span represents an operation with start/end timestamps, such as receiving a request, publishing a message, processing a message, or calling a database.

- **Trace ID:** identifies the entire distributed journey.
- **Span ID:** identifies a specific operation within the trace.
- **Parent span ID:** links the current span to the operation that created it.
- **Baggage:** small contextual values needed across services, such as tenant tier or locale. Baggage does not replace trace ID and must be tightly controlled since it can cross multiple trust boundaries.

When service A publishes a message for service B, B needs to know which trace the message belongs to. Context propagation headers let B create a child span of the publish operation instead of starting a brand-new trace. When B forwards a message to C, C continues that journey.

Without trace context, each service may still emit its own logs and metrics, but the system struggles to answer: "Which services did the initial request pass through, and where did it slow down?"

## 2. W3C Trace Context: traceparent, tracestate, and baggage

W3C Trace Context defines a widely adopted format for exchanging trace context across components.

The **traceparent** header version 00 has the structure:

~~~text
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Parts in order:

| Part | Length in version 00 | Meaning |
| --- | ---: | --- |
| version | 2 hex characters | Format version |
| trace-id | 32 hex characters | ID of the trace |
| parent-id | 16 hex characters | Span ID at the sender side |
| trace-flags | 2 hex characters | Control flags, e.g. sampled |

All-zero IDs are invalid. The header must be parsed according to the specification; do not slice strings at fixed offsets and blindly trust arbitrary input.

**tracestate** carries vendor-specific additional state. It may be updated as context passes through different tracing systems. Typical applications should let the tracing library's propagator handle it rather than modifying the string manually.

**baggage** propagates trace-level key/value pairs. Include only values genuinely needed for cross-service processing. Do not pass access tokens, passwords, personal data, large business payloads, or data that could inflate metric cardinality. When accepting baggage from external sources, allowlist keys, enforce length limits, and apply trust policies.

One critical point: when B receives traceparent from A, B creates a new span with the **same trace ID but a new span ID**. When B sends onward to C, the parent ID in the outgoing header must reference B's span. Do not copy the incoming header verbatim onto every outgoing message, as that breaks the parent-child relationship.

## 3. Spring Message Headers and Transport Headers

In Spring Messaging, a message has two main parts:

- **Payload:** business data.
- **MessageHeaders:** metadata traveling with the message inside Spring, such as ID, timestamp, content type, correlation ID, or custom headers.

You can build a message with headers using MessageBuilder:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> message = MessageBuilder
        .withPayload("order-created")
        .setHeader("traceparent", traceparent)
        .setHeader("tracestate", tracestate)
        .build();
~~~

MessageHeaders is Spring's abstraction metadata. Whether a custom header is transmitted over the network depends on the adapter and transport. Do not assume every internal header automatically becomes an HTTP header, STOMP native header, or RSocket metadata.

Distinguish:

- **Spring Message header:** metadata inside the Spring Messaging pipeline.
- **Transport header/metadata:** fields actually encoded and sent over the wire.
- **Tracing context:** standard content that a propagator injects into and extracts from a carrier.

When crossing a broker or protocol adapter, clearly verify the two-way mapping between MessageHeaders and wire headers/metadata. If an adapter drops custom headers, the trace breaks even though the message still reaches the consumer.

Do not invent pseudo-standard header names such as **x-trace-id** if the system already uses W3C Trace Context. Standardize on the standard names and let Micrometer Tracing choose the propagation format matching your bridge/configuration.

## 4. Injecting and Extracting with Micrometer Tracing

Spring Boot 3 typically integrates Micrometer Observation and Micrometer Tracing. A tracing bridge (such as Brave or OpenTelemetry) provides implementations for creating spans and propagators. For transports that already have automatic instrumentation, prefer that instrumentation. Only inject/extract manually at uninstrumented messaging boundaries to avoid duplicate spans or broken parent links.

Micrometer Tracing provides:

- **Tracer:** creates spans, accesses the current span, and opens scopes.
- **Span:** represents an operation within a trace.
- **Propagator:** injects context into a carrier and extracts context from a carrier.
- **TraceContext:** span context info, including trace ID and span ID.

### Sending a message: create a producer span and inject context

The following example creates a span for a publish operation, injects propagation fields into a Map, and copies them into Spring Message headers:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.propagation.Propagator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

class TracedMessagePublisher {

    private final Tracer tracer;
    private final Propagator propagator;
    private final MessageChannel output;

    TracedMessagePublisher(
            Tracer tracer,
            Propagator propagator,
            MessageChannel output) {
        this.tracer = tracer;
        this.propagator = propagator;
        this.output = output;
    }

    void publish(String payload) {
        Span span = tracer.nextSpan()
                .name("orders.publish")
                .start();

        try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
            Map<String, String> carrier = new LinkedHashMap<>();

            propagator.inject(
                    span.context(),
                    carrier,
                    (headers, key, value) -> headers.put(key, value));

            Message<String> message = MessageBuilder
                    .withPayload(payload)
                    .copyHeaders(carrier)
                    .build();

            output.send(message);
        } finally {
            span.end();
        }
    }
}
~~~

Key points to note:

1. **nextSpan()** creates a new span; if a current span exists, the new span is linked as its child.
2. **withSpan(span)** places the span into the current scope during publish so synchronous logs and instrumentation can see it.
3. **Propagator.inject(...)** writes propagation headers matching the tracing bridge. Never hardcode trace ID or span ID.
4. **copyHeaders(...)** puts the injected fields into the Spring Message. The adapter still needs to transfer these fields onto transport headers/metadata.
5. **finally** ends the span even if sending the message fails.

This code is an integration pattern at the application boundary; MessageChannel, Tracer, and Propagator beans must be configured in the Spring context. If the transport adapter already creates a producer span and injects context automatically, do not wrap the same operation in a second manual producer span.

For asynchronous sends, when the producer span ends should reflect the operation's contract. If send returns immediately after enqueuing, the span only measures enqueue time. If you need to measure broker acknowledgement time, end the span in the corresponding callback/acknowledgement.

### Receiving a message: extract context and create a consumer span

On the consumer side, take the carrier from MessageHeaders and ask the propagator to extract the parent context. Then start a new span for the processing operation:

~~~java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.propagation.Propagator;
import org.springframework.messaging.Message;

class TracedMessageHandler {

    private final Tracer tracer;
    private final Propagator propagator;
    private final OrderService orderService;

    TracedMessageHandler(
            Tracer tracer,
            Propagator propagator,
            OrderService orderService) {
        this.tracer = tracer;
        this.propagator = propagator;
        this.orderService = orderService;
    }

    void handle(Message<String> message) {
        Span.Builder parent = propagator.extract(
                message.getHeaders(),
                (headers, key) -> {
                    Object value = headers.get(key);
                    return value == null ? null : value.toString();
                });

        Span span = tracer.nextSpan(parent)
                .name("orders.process")
                .start();

        try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
            orderService.process(message.getPayload());
        } finally {
            span.end();
        }
    }
}
~~~

If the headers are valid, the consumer span becomes a child of the propagated context. If no context is present, the propagator returns a builder without a parent and the tracing library starts a new trace. Do not let malformed headers break business processing just because of tracing; define a policy for handling malformed context and log it in a controlled manner.

Do not read trace IDs from the business payload if header propagation is already the standard context source. Payloads should preserve domain semantics; tracing metadata belongs in headers or a dedicated carrier.

## 5. Propagating Trace Headers Over STOMP/WebSocket

STOMP carries native headers transmitted inside frames. With Spring, you can use StompHeaderAccessor to set and read these headers.

Example creating a STOMP SEND message with trace context:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.MessageBuilder;

StompHeaderAccessor accessor =
        StompHeaderAccessor.create(StompCommand.SEND);

accessor.setDestination("/app/orders");
accessor.setNativeHeader("traceparent", traceparent);
accessor.setNativeHeader("tracestate", tracestate);
accessor.setLeaveMutable(true);

Message<byte[]> outbound =
        MessageBuilder.createMessage(payloadBytes, accessor.getMessageHeaders());
~~~

On the receiving side, you can read native headers from the STOMP message:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;

StompHeaderAccessor accessor = StompHeaderAccessor.wrap(message);

String traceparent = accessor.getFirstNativeHeader("traceparent");
String tracestate = accessor.getFirstNativeHeader("tracestate");
~~~

If using SimpMessagingTemplate, you can create a SimpMessageHeaderAccessor, call setNativeHeader, and pass MessageHeaders into convertAndSend. Verify that headers actually appear in frames on the wire with an integration test; copying an internal header does not guarantee every adapter transmits it.

Do not stuff trace headers into destinations or alter payloads just to carry context. Native headers are designed for protocol metadata and keep domain payloads independent.

## 6. Preserving Context Across Async Boundaries

A common bug is that context is present on the message-receiving thread but vanishes when processing moves to another thread. Many tracing implementations store the current span in a ThreadLocal. A ThreadLocal is bound only to the currently running thread; when a task moves to another executor or scheduler, the new thread does not automatically inherit the old context.

Boundaries where context is commonly lost:

- @Async or ThreadPoolTaskExecutor.
- Custom ExecutorService instances.
- Reactor publishOn/subscribeOn or callbacks running on another scheduler.
- HTTP/database client callbacks.
- Messages placed into an internal queue and processed by a different worker.

Do not pass a Span object via a static variable or store old spans in a singleton to work around this. Doing so can leak one request's context into another request.

### Using ContextPropagatingTaskDecorator for executors

Spring Framework 6.1 provides ContextPropagatingTaskDecorator to capture and restore contexts registered via Micrometer Context Propagation.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskDecorator;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class MessagingExecutorConfiguration {

    @Bean
    ThreadPoolTaskExecutor messagingExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(200);

        TaskDecorator decorator =
                new ContextPropagatingTaskDecorator();
        executor.setTaskDecorator(decorator);

        return executor;
    }
}
~~~

TaskDecorator captures context when the task is submitted and restores registered context accessors when the task runs. It propagates tracing/logging context across executors, though it does not automatically propagate arbitrary variables. Ensure Micrometer Context Propagation and the tracing bridge are configured properly in the application.

Do not use an unbounded executor queue just to avoid losing context. Queue capacity, rejection policy, and shutdown behavior must still be designed for real load.

### Reactor Context

Reactor executes pipelines across multiple threads but provides Reactor Context to hold subscription-scoped data. This context is not a ThreadLocal. When using Micrometer Context Propagation, tracing context can be bridged between Reactor Context and ThreadLocal according to application configuration.

Example illustrating application-specific correlation data in Reactor Context:

~~~java
import reactor.core.publisher.Mono;

Mono<String> process(String payload, String correlationId) {
    return Mono.deferContextual(context -> {
        String id = context.get("correlationId");
        return Mono.just("processed:" + id + ":" + payload);
    }).contextWrite(context ->
            context.put("correlationId", correlationId));
}
~~~

The snippet above demonstrates Reactor Context for a correlation ID; it does not implement distributed tracing by itself. For trace/span context, use Micrometer Tracing and supported context propagation mechanisms; do not store only a trace ID in Reactor Context and assume parent span, sampling, and baggage are fully preserved.

If enabling Reactor's automatic context propagation, enable it at startup configuration and verify the exact Reactor/Spring version in use. Avoid toggling global hooks arbitrarily between tests because hooks are JVM-global and can affect tests sharing the same JVM.

## 7. Using Observation to Observe Message Processing

Micrometer Observation provides a unified API for timing and adding context to an operation. When the application has a tracing handler/bridge, observations can be exported as spans; when it has a meter handler, they can also produce metrics.

Example instrumenting a handler:

~~~java
import org.springframework.messaging.Message;
import org.springframework.observation.Observation;
import org.springframework.observation.ObservationRegistry;

class ObservedOrderHandler {

    private final ObservationRegistry observationRegistry;
    private final OrderService orderService;

    ObservedOrderHandler(
            ObservationRegistry observationRegistry,
            OrderService orderService) {
        this.observationRegistry = observationRegistry;
        this.orderService = orderService;
    }

    void handle(Message<String> message) {
        Observation.createNotStarted(
                        "messaging.process",
                        observationRegistry)
                .lowCardinalityKeyValue("messaging.system", "spring-messaging")
                .lowCardinalityKeyValue("messaging.operation", "process")
                .observe(() -> orderService.process(message.getPayload()));
    }
}
~~~

Observation names should be stable. Low-cardinality key/values are appropriate for metric dimensions such as messaging system, operation, or destination template. Do not put order ID, user ID, raw message ID, or trace ID into low-cardinality metric tags because that creates massive cardinality.

If a Spring adapter or broker instrumentation already creates an observation/span for this operation, customize the existing instrumentation's convention/tags instead of wrapping the same work in a second observation.

## 8. Correlation ID, Trace ID, and Message ID

These three IDs serve different purposes:

| ID | Purpose | Changes across messages in the same trace? |
| --- | --- | --- |
| Trace ID | Links spans belonging to one distributed journey | Usually stays the same within the trace |
| Span ID | Identifies one specific operation | Every span has its own ID |
| Correlation ID | Links messages belonging to one business workflow | Depends on application contract |
| Message ID | Identifies a specific message for dedup/audit | Every message has its own ID |

A workflow may span minutes or hours, outliving a single trace. Correlation ID can remain stable across that workflow while new traces are started for each processing pass or resumption. Do not use trace ID as a substitute for message ID or idempotency key.

When logging, trace ID and span ID can be placed into MDC so the log backend displays them. Context must be restored/cleared promptly so the next task on the same thread does not inherit stale IDs. Use the tracing library's MDC integration rather than setting ThreadLocals manually without cleanup.

## 9. Security and Data Limits in Headers

Trace context arriving from external requests or messages can be forged. It is useful for observability correlation, not as proof of authentication.

- Do not use trace ID, span ID, or baggage to make authorization decisions.
- Do not put tokens, session cookies, passwords, or sensitive payloads into baggage.
- Forward only allowlisted headers across trust boundaries.
- Limit total header size and number of baggage items.
- Do not trust a tenant ID in baggage when tenants already have an authoritative authentication source.
- Avoid logging raw payloads or entire baggage contents.
- For messages passing through shared brokers, clarify which headers are preserved, stripped, or overwritten.

If traceparent is invalid, the tracing library should handle it per its specification-compliant parser. Applications should not blindly trust invalid values as parents. Depending on policy, start a new trace and record a metric for malformed headers without logging the full raw input.

## 10. Testing Propagation Across Boundaries

A test suite should verify both header contents and span relationships, not just that logs contain an ID string.

| Scenario | How to test | Expected result |
| --- | --- | --- |
| Valid header | Send valid traceparent to consumer | Processing span has the same trace ID and correct parent |
| Onward publish | Consumer emits a new message | Outgoing header references the new producer span |
| Missing header | Send message without trace context | Starts a new trace or follows policy |
| Malformed header | Send malformed traceparent | Invalid context is not used as parent |
| Async executor | Submit task inside a span scope | Task sees the right context; next task sees no leak |
| Reactor scheduler | Switch schedulers in pipeline | Context stays bridged according to configuration |
| Two concurrent messages | Process two traces on the same thread pool | Trace IDs/span IDs do not mix between messages |
| STOMP | Send/receive native headers | Headers are preserved across frames on the wire |
| Broker/adapter | Publish and consume over real transport | Context is not stripped by the adapter |
| Baggage | Send allowlisted and disallowed keys | Only allowed keys are forwarded |

When testing a tracing bridge, use an in-memory span exporter or test tracer suited to your bridge. Assert:

- Downstream span's trace ID matches the incoming trace.
- Downstream span ID differs from the upstream span ID.
- Parent span ID points to the corresponding upstream span.
- Spans have accurate duration and error status when the handler fails.
- Context is closed after processing; the next message does not inherit the old span.

For async executors, create at least two tasks with different trace contexts and deliberately execute them sequentially on the same worker thread. Verify the second task does not see the first task's trace. This catches context leaks that single-task tests often miss.

For real transports, inspect headers at both ends. Unit tests only verify MessageBuilder holds headers in memory; they do not prove STOMP, RSocket, or a broker adapter serialized and transmitted those headers.

## 11. Common Mistakes

- **Propagating only trace ID:** downstream does not know the parent span, so the trace tree breaks or links inaccurately.
- **Copying incoming traceparent verbatim onto the next message:** parent ID fails to reflect the current span.
- **Assuming MessageHeaders always cross the network:** adapters may only forward a supported subset of headers.
- **Using ThreadLocal across @Async without a decorator:** worker threads have no context or retain stale context.
- **Creating manual spans when instrumentation already creates them:** traces show duplicate spans for the same operation.
- **Putting high-cardinality IDs into metric tags:** metrics backend series counts explode.
- **Putting sensitive data into baggage:** data can travel across multiple services and show up in telemetry.
- **Using trace ID as an idempotency key:** traces can change on retry and do not guarantee uniqueness per business operation.
- **Checking logs only:** an ID in logs does not prove accurate parent-child relationships or span timings.

## 12. Implementation Checklist

- [ ] Choose W3C Trace Context or a single unified propagation format across the system.
- [ ] Create producer spans and consumer spans at the exact messaging boundaries.
- [ ] Use Micrometer Propagator to inject/extract rather than assembling traceparent manually.
- [ ] Verify custom MessageHeaders map to transport headers/metadata.
- [ ] Preserve context across executors and Reactor using supported mechanisms.
- [ ] Close scopes and spans even when processing errors or cancels.
- [ ] Avoid creating spans that duplicate automatic instrumentation.
- [ ] Use correlation ID, message ID, and idempotency key for their intended purposes.
- [ ] Enforce allowlists, size limits, and zero secrets in baggage.
- [ ] Test valid headers, missing/malformed headers, async, concurrency, and real transports.
- [ ] Keep raw payloads and unnecessary high-cardinality tags out of logs and metrics.

## References

- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [W3C Baggage](https://www.w3.org/TR/baggage/)
- [Spring Framework Reference — Messaging](https://docs.spring.io/spring-framework/reference/integration.html)
- [Spring Framework Reference — WebSocket STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html)
- [Spring Framework API — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
