# Propagating Context and Per-Element Observability in a Stream

In a Spring Cloud Stream application using Reactor, a `Flux<T>` can process multiple messages across different threads. Therefore, information needed for a given processing unit—such as `correlationId`, `eventId`, tenant, trace, or security information—cannot be managed casually via global variables or `ThreadLocal` under the assumption that it always stays attached to the message.

To propagate context and observe each element accurately, distinguish three storage locations: **message payload and headers** carry data along with the message across the broker; **Reactor Context** carries context bound to a subscription inside the reactive pipeline; **MDC/ThreadLocal** serves logging on the current thread and requires context propagation when the pipeline switches threads. Combining these mechanisms properly lets you trace an event across many steps without mixing context across messages.

## 1. Three Types of Context in a Reactive Stream

A message may require several kinds of information, not all of which belong to the same scope:

| Storage location | Scope | Example | Crosses broker automatically? |
|---|---|---|---|
| Payload | Business data of the message | `orderId`, `amount`, `status` | Yes, if the payload is serialized. |
| Message headers | Metadata attached to a message | `eventId`, `correlationId`, `tenantId`, `contentType`, trace headers | Only when binder/broker mapping and header propagation config support it. |
| Reactor Context | Context of a reactive subscription | Trace/observation context, security context, data for operators in the pipeline | No; metadata must be explicitly copied to the message when crossing the broker. |
| MDC/ThreadLocal | Context on the current thread | `traceId`, `correlationId` for logging | No; exists only inside the process and thread where the value is set. |

For example, `eventId` identifies a specific event so it typically resides in the message's payload or headers. `correlationId` links multiple messages belonging to the same business workflow so it is usually passed via headers. Reactor Context can carry trace context or security context while the pipeline executes. MDC is simply a way to inject values into logs on the current thread.

Do not use Reactor Context as a substitute for payload or message headers when data must cross the broker. Reactor Context is not automatically serialized with the message.

## 2. What Is Reactor Context?

Reactor Context is a key-value structure attached to a subscriber/subscription. Operators can read the context via `deferContextual`, while `contextWrite` creates or updates context for the upstream portion of the pipeline.

Several key characteristics:

- Context is tied to a subscription, not permanently bound to a thread.
- Context is immutable by API; write operations return a new Context.
- Context flows across Reactor operators within the same pipeline/subscription.
- `contextWrite` affects upstream operators in the subscription direction, so its placement is critical.
- Context is not an automatic per-element storage area for each item in a `Flux`.

Minimal example:

```java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

Mono<String> greeting = Mono.deferContextual(context -> {
    String requestId = context.getOrDefault("requestId", "unknown");
    return Mono.just("request=" + requestId);
}).contextWrite(Context.of("requestId", "req-1001"));
```

`deferContextual` reads context only upon subscription. `contextWrite` provides `requestId` to the upstream portion of the publisher. The result is `request=req-1001`.

If you read context outside the publisher before subscription occurs, there is no subscription context to access. Therefore, do not treat `ContextView` as if it were a global variable.

## 3. Distinguishing Subscription Context from Per-Message Data

A common misconception is assuming every element in a `Flux` has its own separate Reactor Context. In reality, Reactor Context belongs to the subscription. If one subscription emits thousands of elements, that subscription's context is shared by operators processing those elements.

If each message has a different `correlationId`, extract the ID from the message's own header/payload. You can create an inner publisher per message and write the value into that inner subscription's context:

```java
import org.springframework.messaging.Message;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

// messages is a Flux<Message<String>> received from the input binding.
Flux<String> descriptions = messages.flatMap(message ->
    {
        String messageCorrelationId = message.getHeaders()
            .get("correlationId", String.class);
        return Mono.deferContextual(context -> {
            String correlationId = context.get("correlationId");
            return Mono.just(correlationId + ": " + message.getPayload());
        }).contextWrite(context -> context.put(
            "correlationId",
            messageCorrelationId == null ? "unassigned" : messageCorrelationId
        ));
    }
);
```

Each message creates an inner publisher. `contextWrite` on the inner publisher supplies that message's correlation ID to the corresponding `deferContextual`. This inner subscription's context does not overwrite the context of other messages inside the same `flatMap`.

Even so, context does not replace headers. When results must be sent to a broker or another service, copy or reconstruct necessary metadata in the output `Message<?>`.

## 4. Feeding Message Metadata into a Reactive Pipeline

With Spring Cloud Stream, a function can accept `Flux<Message<T>>` to access both payload and headers of each message. This is helpful when processing needs per-message `eventId`, `correlationId`, tenant, or trace metadata.

Example of a function processing order events:

```java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Configuration
class OrderContextFunctions {

    @Bean
    Function<Flux<Message<OrderCreated>>, Flux<Message<OrderProcessed>>> processOrders(
            OrderService orderService) {
        return messages -> messages.flatMap(message -> {
            String correlationId = message.getHeaders()
                .get("correlationId", String.class);

            return Mono.deferContextual(context ->
                orderService.process(
                    message.getPayload(), context.get("correlationId"))
                    .map(result -> MessageBuilder.withPayload(result)
                        .copyHeaders(message.getHeaders())
                        .build())
            ).contextWrite(context -> context.put(
                "correlationId",
                correlationId == null ? "unassigned" : correlationId
            ));
        });
    }
}

record OrderCreated(String eventId, String orderId) {}
record OrderProcessed(String eventId, String orderId, String status) {}
```

This example demonstrates three things:

1. Reading `correlationId` from each message's headers.
2. Putting that value into the inner publisher's Reactor Context so downstream reactive components can read it.
3. Building the output message and copying headers to retain necessary metadata.

In real applications, define clearly which headers may be forwarded. Do not blindly copy every header—especially credentials, internal broker headers, or sensitive data. Use `MessageBuilder` to select only required headers and update modified values.

## 5. contextWrite and Operator Placement

`contextWrite` provides context to upstream operators. This means its position in the operator chain governs where values can be read.

```java
Mono<String> result = Mono.deferContextual(ctx ->
    Mono.just(ctx.get("tenantId"))
).contextWrite(ctx -> ctx.put("tenantId", "tenant-42"));
```

In this example, `deferContextual` sits upstream relative to `contextWrite`, so it can read `tenantId`. Placing a context-reading operator downstream of `contextWrite` will not automatically see values written for upstream.

In complex pipelines, place `deferContextual` where context actually needs to be read and place `contextWrite` at the right subscription scope. When using `flatMap`, if different context is needed per message, place `contextWrite` inside the publisher created for each element instead of writing a changing value to the shared context of the outer `Flux`.

## 6. Context Propagation Across Thread Switches

Reactor can switch execution across threads due to `publishOn`, `subscribeOn`, schedulers, or asynchronous libraries. Reactor Context follows the subscription, whereas `ThreadLocal` and MDC are bound to a thread. Hence, a value placed in MDC on thread A does not automatically appear on thread B.

For instance, the snippet below does not guarantee MDC still has `correlationId` in the callback after switching schedulers:

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

MDC.put("correlationId", "corr-1001");

return service.loadOrder()
    .publishOn(Schedulers.parallel())
    .doOnNext(order -> log.info("Loaded {}", order.id()));
```

The `doOnNext` callback may run on a different thread whose MDC lacks the value set on the initial thread. Moreover, without cleaning up MDC properly, a reused thread can leak the previous message's data into a subsequent message.

To solve this, use Micrometer Context Propagation and its Reactor integration. Registered `ThreadLocalAccessor` instances allow capturing/restoring values from the appropriate context. Reactor supports limited propagation and automatic mode; automatic mode can be enabled via `Hooks.enableAutomaticContextPropagation()` before creating subscriptions that need it. In Spring Boot applications, check context propagation configuration and the Reactor/Micrometer versions in use, as automatic integration depends on versions and dependencies.

Do not enable the hook repeatedly per message or per function. This is application-level configuration that should be initialized once according to your framework version's guidance.

## 7. Using MDC Safely When Logging

MDC is commonly used to attach `correlationId`, `eventId`, or `traceId` to every log line on the current thread. If logging directly from a callback, ensure the value is restored/removed right after the callback.

Example of a local MDC scope:

```java
import org.slf4j.MDC;

void logOrder(OrderCreated event, String correlationId) {
    String previous = MDC.get("correlationId");
    try {
        if (correlationId == null) {
            MDC.remove("correlationId");
        } else {
            MDC.put("correlationId", correlationId);
        }
        log.info("Processing order {}", event.orderId());
    } finally {
        if (previous == null) {
            MDC.remove("correlationId");
        } else {
            MDC.put("correlationId", previous);
        }
    }
}
```

This snippet scopes MDC within a single synchronous callback. If logs are emitted across multiple callbacks on different schedulers, use appropriate context propagation or create a local MDC scope inside each callback. Never leave MDC open across an asynchronous publisher and close it on another thread.

In applications using Micrometer Tracing, prefer Spring Boot and Micrometer's tracing/context propagation integration so trace ID/span ID appear consistently in logs. Do not generate a new trace ID per operator if you want a single trace across a processing unit.

## 8. Per-Element Observability: Logs, Metrics, and Traces

The three observability signals serve different purposes:

| Signal | Answers the question | Example |
|---|---|---|
| Structured logs | What happened to a specific message? | `eventId`, `orderId`, `correlationId`, processing status. |
| Metrics | How is the system behaving over time? | Messages/second, error rate, processing latency, backlog. |
| Traces/spans | Which services and steps did the message traverse? | Spans for receiving message, calling service, writing database, emitting next event. |

Each message can carry its own `eventId` for log lookup. `correlationId` ties together multiple messages in one workflow. Trace context such as W3C `traceparent` and `tracestate` or equivalent formats connects spans across service boundaries, provided producers, binders, and consumers propagate those headers properly.

Do not put `eventId`, `orderId`, `correlationId`, or high-cardinality tenant IDs into standard metric tags. High-cardinality values explode time series counts and storage costs. Put them in logs or traces; metric tags should use bounded sets of values such as `operation`, `result`, `message_type`, or `error_category`.

## 9. Creating an Observation for a Message

Micrometer Observation provides a unified API for timing and creating context for registered metric/trace handlers. For a reactive publisher, the Observation lifecycle should follow the subscription lifecycle and stop when the publisher completes, errors, or is cancelled.

Illustrative example creating an Observation per message:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import reactor.core.publisher.Mono;

Mono<OrderProcessed> observeOne(
        OrderCreated event,
        OrderService service,
        ObservationRegistry registry) {

    return Mono.defer(() -> {
        Observation observation = Observation
            .createNotStarted("orders.process", registry)
            .lowCardinalityKeyValue("operation", "process-order");

        observation.start();
        return Mono.defer(() -> service.process(event))
            .doOnSuccess(result -> observation.lowCardinalityKeyValue(
                "result", result == null ? "empty" : "success"))
            .doOnError(observation::error)
            .doFinally(signal -> observation.stop());
    });
}
```

`Mono.defer` creates a new Observation for each message subscription. `doOnError` records the exception and `doFinally` stops the Observation on completion, error, or cancellation. In production code, ensure the Observation is started/stopped exactly once and its context integrates with Micrometer Context Propagation if logs/traces must correlate across schedulers.

Use low-cardinality keys only for bounded-value fields. Never attach `eventId` or `orderId` to low-cardinality metric tags. If specific identifiers must be included in traces, use high-cardinality attributes according to your system's telemetry policy.

## 10. Propagating Trace Context Across the Broker

Reactor Context exists only within the current subscription. When a function emits a new message via an output binding, if trace linkage between producer and consumer must be preserved, context must be injected into headers per the system's propagation standard.

With W3C Trace Context, common headers are:

- `traceparent`: contains trace ID, parent span ID, and flags.
- `tracestate`: carries optional vendor-specific details.

Spring/Micrometer tracing libraries can inject/extract these headers when configured and integrated with messaging instrumentation. Still, header transmission across a broker depends on binder header mapping, native header settings, and broker header limits. Test on a real binder to confirm consumers receive trace context.

If manually propagating a business `correlationId`, set explicit headers on the output message:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderProcessed> output = MessageBuilder
    .withPayload(result)
    .setHeader("correlationId", correlationId)
    .setHeader("eventId", result.eventId())
    .build();
```

Do not fabricate or modify `traceparent` manually. Use the tracing library's propagator to ensure valid structure and parent/child relationships. Business correlation IDs and trace IDs are distinct concepts; a single business workflow can span multiple traces across calls or asynchronous steps.

## 11. Context in Asynchronous Operators

Operators such as `flatMap`, `publishOn`, and `subscribeOn` can make control flow more complex. Reactor Context propagates along the subscription, yet per-element data should still live in the message or be enclosed within its corresponding inner publisher.

For example, with two messages having different correlation IDs:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

// service is an OrderService injected into the processing component.
Message<String> first = MessageBuilder.withPayload("order-1")
    .setHeader("eventId", "evt-1")
    .setHeader("correlationId", "corr-A")
    .build();
Message<String> second = MessageBuilder.withPayload("order-2")
    .setHeader("eventId", "evt-2")
    .setHeader("correlationId", "corr-B")
    .build();

Flux<String> outputs = Flux.just(first, second)
    .flatMap(msg -> Mono.deferContextual(ctx ->
        service.describe(msg.getPayload())
            .map(description -> ctx.get("correlationId") + ":" + description)
    ).contextWrite(ctx -> ctx.put(
        "correlationId",
        msg.getHeaders().get("correlationId", String.class)
    )));
```

Each inner publisher receives context values from its corresponding message headers. Results do not mix between `corr-A` and `corr-B` even when both messages are processed concurrently.

When using `flatMap`, bound concurrency if dependent services have load limits. If output ordering is required, consider `concatMap` or `flatMapSequential`. Having the right context does not by itself guarantee business completion order.

## 12. Security Context and Tenant Context

A pipeline may require user or tenant information. With reactive Spring Security, `SecurityContext` is stored in Reactor Context and accessed via Spring Security's reactive APIs. Do not read `SecurityContextHolder` imperatively inside a reactive callback and assume it is always present on the current thread.

Tenant ID may be business or routing metadata. If a tenant is read from a message header, validate that the tenant falls within the scope that the producer is authorized to send. Do not trust a `tenantId` header merely because it came from the broker; a broker can receive messages from multiple producers or untrusted sources.

Do not pass access tokens, passwords, or credentials via event headers unless genuinely necessary. If consumers must verify permissions, use service identity and service-to-service authentication; business context does not replace access control checks.

## 13. Common Context Propagation Pitfalls

| Error | Cause | Resolution |
|---|---|---|
| MDC is empty after `publishOn` | MDC is ThreadLocal and the callback runs on another thread. | Use Micrometer Context Propagation or scope MDC inside the callback. |
| Next message carries previous message's correlation ID | ThreadLocal was not cleared/restored when the thread was reused. | Use a `try/finally` scope; never store message state in singleton fields. |
| `deferContextual` cannot find key | `contextWrite` was placed in the wrong position or key was not written for that subscription. | Check upstream direction and place `contextWrite` on the right inner publisher. |
| Two elements share one correlation ID | Writing a shared context for the whole subscription instead of reading ID from each message. | Read metadata from each message and create separate inner publishers when needed. |
| Trace breaks across the broker | Trace headers were not injected, mapped, or extracted properly. | Check tracing instrumentation and binder header mapping. |
| Reactor Context disappears after sending message | Context is not serialized automatically across the broker. | Copy required metadata into message headers/payload. |
| Metrics have too many time series | Putting event ID/order ID into metric tags. | Move identifiers to logs/traces; keep metric tags low-cardinality. |

## 14. Testing Context and Observability

Test context logic, message headers, and binder transmission separately.

### Testing Reactor Context

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

class ReactorContextTest {

    @Test
    void readsContextFromSubscription() {
        Mono<String> source = Mono.deferContextual(ctx ->
            Mono.just(ctx.get("correlationId"))
        );

        StepVerifier.create(source.contextWrite(
                Context.of("correlationId", "corr-1001")))
            .expectNext("corr-1001")
            .verifyComplete();
    }
}
```

### Testing Per-Element Isolation of Context

Create two messages with two different correlation IDs, process them concurrently through `flatMap`, and verify outputs still stay paired with the right IDs. This test catches bugs caused by sharing a mutable variable or writing context in the wrong scope.

### Testing MDC and Thread Switches

If the application uses MDC, test callbacks before and after `publishOn`/`subscribeOn`, verifying trace/correlation metadata is restored and never leaks to the next task on the same thread. With Micrometer Context Propagation, test registered accessors and configured propagation modes.

### Testing the Binder

Use the Spring Cloud Stream Test Binder to send messages with headers through bindings and verify output headers. The Test Binder does not fully simulate real broker header mapping; run integration tests against Kafka, RabbitMQ, or Pulsar when relying on native headers, trace propagation, or broker metadata limits.

## 15. Operational Checklist

Before promoting a reactive function to production, verify:

1. Are `eventId` and `correlationId` placed in the payload/headers with the right scope?
2. Is metadata crossing the broker serialized/mapped and tested on the consumer?
3. Is Reactor Context placed on the right subscription and at the right position in the pipeline?
4. Is per-message context derived from each message rather than sharing a mutable variable?
5. Is MDC restored or cleared on every exit path of callbacks?
6. Is context propagation across schedulers configured properly for your Reactor/Micrometer/Spring Boot versions?
7. Are trace headers injected/extracted using a propagator instead of hand-crafted?
8. Are metric tags low-cardinality, with message identifiers logged/traced instead?
9. Is tenant/security metadata validated and free of sensitive credentials?
10. Are there tests covering context, thread switches, header mapping, and real binders at critical boundaries?

Propagating context properly ensures every element in a stream retains its own identity and processing trail. Using message headers for metadata crossing the broker, Reactor Context for subscription context, and context propagation for MDC/ThreadLocal across thread switches gives Spring Cloud Stream reliable logs, metrics, and traces without mixing data across messages.
