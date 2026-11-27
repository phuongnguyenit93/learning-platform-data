# Propagating Tracking IDs Through Reactive Context

In a Spring WebFlux application combined with Spring Data R2DBC, a single request can pass through multiple layers and multiple threads: `WebFilter`, Controller, Service, Repository, the R2DBC driver, and external HTTP services. To link logs and follow a request across those layers, applications typically need a correlation ID or trace information (trace ID/span ID).

In imperative applications, per-request metadata is typically stored in `ThreadLocal` or MDC. That approach is not reliable enough in a reactive pipeline because a request can resume on a different thread after `publishOn`, `flatMap`, or an I/O operation. Reactor provides **Context** attached to a subscription to pass metadata along the reactive flow, independent of the current thread.

In the Spring reactive stack, Reactor Context is also used by foundational mechanisms such as reactive transaction management and observability. Therefore, when propagating a correlation ID, add values to the Context in a way that preserves existing entries; do not replace the entire Context or move metadata into a global variable. For MDC/`ThreadLocal`-based logging, use a proper context propagation bridge or set MDC strictly within a synchronous callback scope.

## 1. What Are Correlation IDs and Trace IDs Used For?

Two types of IDs frequently appear in observability:

- **Correlation ID:** an application-level code used to link logs or operations belonging to the same request/workflow. It is usually received from an HTTP header or generated at the edge/first service.
- **Trace ID:** an identifier for a distributed trace composed of multiple spans across services. Trace IDs belong to the distributed tracing model, typically following W3C Trace Context or the tracing system's format.
- **Span ID:** an identifier for a unit of work within a trace, such as an HTTP server request, an HTTP client call, or an instrumented database operation.

Correlation IDs and trace IDs can be linked or, in simple systems, share a value, though semantically they are not inherently identical. Traces model parent-child relationships and sampling; correlation IDs are typically application-managed log search keys.

Example:

~~~text
HTTP request
  X-Correlation-ID: req-7f2a...
  traceparent: 00-4bf92f...-00f067...-01

Application log:
  correlationId=req-7f2a...
  traceId=4bf92f...
  spanId=00f067...
~~~

When using Micrometer Tracing or OpenTelemetry, let the tracing library manage trace/span IDs and propagation headers. Do not generate your own trace IDs and overwrite trace metadata already established by the tracing system.

## 2. Why ThreadLocal Is Insufficient in Reactive Code

`ThreadLocal` stores values bound to a specific thread. In a reactive model, the thread handling a signal may differ from the thread that started the request:

~~~java
return repository.findById(id)
        .publishOn(Schedulers.parallel())
        .map(this::toResponse);
~~~

A publisher can run different stages on different threads. With `flatMap`, multiple inner publishers can run concurrently, with signals handled by different threads.

If you merely write:

~~~java
MDC.put("correlationId", correlationId);
return service.findSomething();
~~~

the MDC value may be missing on the thread executing a later callback. Worse, thread pools reuse threads; failing to clear MDC properly lets a subsequent request see leftover values from a previous request.

Reactor Context solves metadata propagation by tying it to the subscription rather than thread identity. Context remains readable when the pipeline switches threads, as long as operations stay within the same reactive chain and are not split into detached subscriptions.

## 3. What Is Reactor Context?

Reactor Context is an immutable key/value structure bound to a subscriber. It typically holds small metadata such as:

- Correlation ID.
- Trace context or baggage managed by tracing integrations.
- Verified tenant information.
- Security context in reactive security.
- Spring-managed transaction resources.
- Internal per-request control flags.

Context is not a shared mutable `Map` across the application. Operators produce a new Context version when adding or updating keys. Each subscription has its own Context, so two concurrent requests can use the same key while carrying different values.

Example:

~~~java
static final String CORRELATION_ID = "app.correlationId";

Mono<String> publisher = Mono.deferContextual(context ->
        Mono.just(context.get(CORRELATION_ID))
);

Mono<String> request = publisher.contextWrite(context ->
        context.put(CORRELATION_ID, "req-123")
);
~~~

When the subscriber runs, `deferContextual` reads the value from the subscription's Context and emits `req-123`.

## 4. Reading Context with deferContextual

`deferContextual` lets you construct a publisher based on the Context available at subscription time:

~~~java
public Mono<String> currentCorrelationId() {
    return Mono.deferContextual(context -> {
        String id = context.getOrDefault(
                CORRELATION_ID,
                "unknown"
        );
        return Mono.just(id);
    });
}
~~~

You can check `context.hasKey(...)` before reading a required key:

~~~java
return Mono.deferContextual(context -> {
    if (!context.hasKey(CORRELATION_ID)) {
        return Mono.error(
                new IllegalStateException("Correlation ID is missing")
        );
    }

    return Mono.just(context.get(CORRELATION_ID));
});
~~~

If the metadata is only for logging and may be absent on some internal paths, `getOrDefault` is usually appropriate. If the metadata is mandatory for business or security logic, validate it at the request boundary and fail explicitly instead of silently falling back to a default.

## 5. Writing Context with contextWrite

`contextWrite` updates the Context seen by upstream operators:

~~~java
Mono<String> result = currentCorrelationId()
        .contextWrite(context ->
                context.put(CORRELATION_ID, "req-456")
        );
~~~

A common point of confusion: Context flows from downstream subscribers to upstream operators during subscription. Therefore, `contextWrite` is typically placed at the end of the chain so earlier publishers can read the value:

~~~java
return service.findSomething()
        .map(this::toResponse)
        .contextWrite(context ->
                context.put(CORRELATION_ID, correlationId)
        );
~~~

You do not need `contextWrite` in every layer. Once a `WebFilter` puts the correlation ID into the request's Context, properly chained publishers underneath can read it.

When adding a key, pass a function receiving the current Context:

~~~java
.contextWrite(context -> context.put(CORRELATION_ID, id))
~~~

Avoid replacing the Context with a brand-new Context lacking previous entries:

~~~java
// Avoid if you need to preserve transaction, security, or tracing context.
.contextWrite(Context.of(CORRELATION_ID, id))
~~~

Replacing the entire Context can wipe out transaction resources or metadata attached by Spring and tracing infrastructure. Mutate the Context passed into the callback to keep existing keys intact.

## 6. Putting the Correlation ID into Context in a WebFilter

A `WebFilter` is the right place to extract or generate a correlation ID once at the HTTP boundary. The filter can:

1. Read the correlation header from the request.
2. Validate its format and length.
3. Generate a new ID if missing or invalid.
4. Write the ID to the response header.
5. Place the ID into Reactor Context for downstream processing.

Example:

~~~java
import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class CorrelationIdWebFilter implements WebFilter {

    public static final String HEADER = "X-Correlation-ID";
    public static final String CONTEXT_KEY = "app.correlationId";

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,128}");

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String supplied = exchange.getRequest()
                .getHeaders()
                .getFirst(HEADER);

        String correlationId = isValid(supplied)
                ? supplied
                : UUID.randomUUID().toString();

        exchange.getResponse()
                .getHeaders()
                .set(HEADER, correlationId);

        return chain.filter(exchange)
                .contextWrite(context ->
                        context.put(CONTEXT_KEY, correlationId)
                );
    }

    private boolean isValid(String value) {
        return value != null && SAFE_ID.matcher(value).matches();
    }
}
~~~

This example uses a regex restricting characters and length to prevent malformed headers or log injection. Real policies may choose to always generate a server-side UUID rather than trusting client-supplied IDs. If external IDs are accepted, define which clients may supply them and never treat the value as proof of identity.

Response headers are set before the response commits. If the application has another filter setting correlation IDs, standardize on a single source of generation and filter order so they do not overwrite each other.

## 7. Why Validate the Correlation Header?

Correlation IDs are commonly logged and may appear in responses or traces. Never accept arbitrary unbounded strings:

- Overly long strings can bloat logs and headers.
- Newline characters can cause log injection if logged unsafely.
- Values containing personal data or secrets can be persisted across multiple systems.
- Clients might intentionally reuse the same ID across requests to confuse investigations.

A common strategy:

- Cap length, e.g., maximum 128 characters.
- Allow only a simple character set.
- Generate a new UUID when missing or malformed.
- Keep tokens, emails, names, or business data out of the ID.
- Optionally record invalid incoming headers separately via sanitized metrics/logs.

A correlation ID is metadata for tracing/lookup, not a secret, session token, or authorization credential.

## 8. Reading the Correlation ID in a Service

A service can read Context when metadata is genuinely needed:

~~~java
public Mono<Order> createOrder(CreateOrderCommand command) {
    return Mono.deferContextual(context -> {
        String correlationId = context.getOrDefault(
                CorrelationIdWebFilter.CONTEXT_KEY,
                "unknown"
        );

        log.info("Creating order, correlationId={}", correlationId);

        return orderRepository.save(toOrder(command));
    });
}
~~~

However, you do not need to read Context in every method just to log. Automatic logging/tracing integrations can attach metadata for you. If a service needs a correlation ID to call an external system or record an audit entry, consider passing a strongly typed request/workflow context parameter rather than coupling every domain method to Reactor Context.

Reactor Context fits cross-cutting metadata; business data required for correctness should appear explicitly in commands or method parameters.

## 9. Attaching the Correlation ID to Logs via MDC

SLF4J MDC usually relies on `ThreadLocal`. Reactor Context does not synchronize with MDC automatically unless a proper context propagation mechanism is enabled.

A manual pattern is reading Context and setting MDC only for the synchronous logging callback:

~~~java
return orderRepository.findById(orderId)
        .doOnNext(order ->
                Mono.deferContextual(context -> {
                    String id = context.getOrDefault(
                            CorrelationIdWebFilter.CONTEXT_KEY,
                            "unknown"
                    );
                    return Mono.fromRunnable(() -> {
                        try (var ignored = MDC.putCloseable(
                                "correlationId", id)) {
                            log.info("Order loaded: {}", order.id());
                        }
                    });
                }).subscribe()
        );
~~~

The snippet above **should not be used** because the `doOnNext` callback spawns an independent subscription via `subscribe()`; it detaches work from the main pipeline. Avoid this pattern.

A proper way to observe inside the pipeline is `doOnEach` and `Signal.getContextView()`:

~~~java
return orderRepository.findById(orderId)
        .doOnEach(signal -> {
            if (!signal.isOnNext()) {
                return;
            }

            String id = signal.getContextView().getOrDefault(
                    CorrelationIdWebFilter.CONTEXT_KEY,
                    "unknown"
            );

            try (var ignored = MDC.putCloseable("correlationId", id)) {
                log.info("Order loaded: {}", signal.get().id());
            }
        });
~~~

MDC exists only during that synchronous logging callback and is restored/cleared when the scope closes. Do not assume MDC remains present in subsequent callbacks or on other threads.

If you want every log across the call stack to carry the correlation ID automatically, use Micrometer Context Propagation or tracing integration instead of adding `doOnEach` to every publisher.

## 10. Micrometer Context Propagation and ThreadLocalAccessor

Micrometer Context Propagation bridges context mechanisms such as Reactor Context and `ThreadLocal`. A `ThreadLocalAccessor` describes how to read, write, and clear a `ThreadLocal` value; context snapshots restore those values when callbacks run on another thread.

Concept:

~~~text
Reactor Context
    correlationId = req-123
          |
          v
Context Propagation
          |
          v
ThreadLocal / MDC
    correlationId = req-123
          |
          v
Synchronous log statement
          |
          v
Restore / clear ThreadLocal
~~~

When using MDC, register an appropriate accessor or use the integration provided by your tracing/logging stack. Avoid writing custom accessors if your application already has bridges from Micrometer Tracing, Brave, OpenTelemetry, or your logging library.

Context propagation must restore prior `ThreadLocal` state and clear values when leaving scope. Setting MDC without cleanup risks leaking metadata across requests in thread pools.

## 11. Enabling Reactor Automatic Context Propagation

Reactor supports integration with Micrometer Context Propagation. In Reactor versions supporting this API, you can enable automatic context propagation:

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Hooks;

@Configuration
public class ReactorContextConfiguration {

    @PostConstruct
    public void enableContextPropagation() {
        Hooks.enableAutomaticContextPropagation();
    }
}
~~~

The exact API and behavior depend on Reactor Core and Micrometer Context Propagation versions. Check the Spring Boot-managed versions and corresponding documentation before adding configuration. Automatic mode can introduce overhead from capturing/restoring `ThreadLocal`s; enable it only when the application needs that bridge and you have measured its impact.

In Spring Boot, some versions provide a configuration property for Reactor context propagation mode. Exact property names and valid values depend on the Boot version; check your project's configuration metadata instead of copying a property from another version.

Automatic propagation does not replace putting the correlation ID into Reactor Context. It only helps restore values already registered/stored in context through supported mechanisms.

## 12. contextCapture and Context Propagation

Micrometer Context Propagation can capture registered `ThreadLocal`s into a snapshot. Reactor provides the `contextCapture()` operator in matching integration versions to copy that snapshot into Context at subscription time.

Conceptual pattern:

~~~java
Mono<Result> result = service.execute()
        .contextCapture();
~~~

This is useful when an imperative library sets metadata in `ThreadLocal` before creating a subscription and the application wants to capture it into Reactor Context.

In WebFlux, the preferred direction is placing request metadata into Reactor Context inside a `WebFilter`, then using propagation bridges for code requiring `ThreadLocal`/MDC. Do not rely on a `ThreadLocal` set on the HTTP-receiving thread remaining intact throughout pipeline execution.

## 13. Tracing with Micrometer Observation and Micrometer Tracing

An application-managed correlation ID is one layer of metadata. Distributed tracing should use a dedicated framework:

- **Micrometer Observation:** operation observation API capable of driving metrics and tracing handlers.
- **Micrometer Tracing:** abstraction for traces/spans and propagation.
- **OpenTelemetry or Brave bridge:** concrete backend/tracer implementation.
- **W3C Trace Context:** standard for propagating traces via HTTP headers such as `traceparent` and optional `tracestate`.

Spring Boot Actuator and Micrometer Tracing can auto-instrument several framework boundaries when matching dependencies and configurations are added. Do not assume every R2DBC command or SQL query gets an automatic span; support depends on versions, drivers, and configured instrumentation.

When tracing already manages trace context, never overwrite the trace ID with a correlation ID. To link the two, record the correlation ID as a controlled span/log attribute.

## 14. Propagating Correlation IDs via WebClient

When a service calls another HTTP service, it can forward the correlation ID in a header. Use a `WebClient` filter that reads Reactor Context at subscription time:

~~~java
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import reactor.core.publisher.Mono;

public class CorrelationWebClientFilter {

    public static ExchangeFilterFunction propagate() {
        return (request, next) ->
                Mono.deferContextual(context -> {
                    String id = context.getOrDefault(
                            CorrelationIdWebFilter.CONTEXT_KEY,
                            null
                    );

                    if (id == null) {
                        return next.exchange(request);
                    }

                    ClientRequest updated = ClientRequest.from(request)
                            .headers(headers ->
                                    headers.set(
                                            CorrelationIdWebFilter.HEADER,
                                            id
                                    )
                            )
                            .build();

                    return next.exchange(updated);
                });
    }
}
~~~

Registering the filter:

~~~java
@Bean
WebClient webClient(WebClient.Builder builder) {
    return builder
            .filter(CorrelationWebClientFilter.propagate())
            .build();
}
~~~

If the application uses distributed tracing, let tracing instrumentation manage `traceparent`. A custom correlation header can still be forwarded alongside it if services rely on it for log searches.

Do not send correlation IDs or arbitrary baggage to every external host. Propagate only to trusted dependencies and avoid sending sensitive data.

## 15. Propagating Trace Context Using the W3C Standard

W3C Trace Context defines primary headers:

- `traceparent`: contains version, trace ID, parent span ID, and trace flags.
- `tracestate`: optional, contains vendor-specific information.

An example header looks like:

~~~text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Do not parse and reconstruct this header manually in application code when using Micrometer Tracing/OpenTelemetry. The tracing propagator must handle validation, child span creation, and standard-compliant injection/extraction.

When a request enters a service, instrumentation extracts context from headers. When calling another service, client instrumentation creates a child span and injects the corresponding context. The trace ID stays constant end-to-end, while the span ID changes per unit of work.

## 16. Passing Metadata Across Multiple Service Layers

If a method needs the correlation ID solely for logging, read Reactor Context at the logging point or rely on a logging bridge. If the ID is a business input, pass it as a parameter:

~~~java
public Mono<Order> createOrder(
        CreateOrderCommand command,
        String requestId) {

    log.info("Creating order, requestId={}", requestId);
    return orderRepository.save(toOrder(command));
}
~~~

Do not turn Reactor Context into a dumping ground for every parameter. Context fits cross-cutting metadata; explicit parameters make business dependencies clear, easy to test, and independent of runtime context.

## 17. Reactor Context and Transaction Context Coexisting

Spring reactive transaction management stores transaction resources in Reactor Context. Therefore, adding a correlation ID must preserve existing keys:

~~~java
return transactionalOperator.transactional(
        orderRepository.save(order)
)
.contextWrite(context ->
        context.put(CorrelationIdWebFilter.CONTEXT_KEY, correlationId)
);
~~~

Never replace the Context with an instance holding only the correlation ID. Losing transaction resources can prevent repositories from participating in the intended transaction; other contexts like security or observation can also break.

When chaining multiple `contextWrite` calls, operator ordering and duplicate keys can overwrite values. Use clearly namespaced keys, assign a single place to initialize the correlation ID, and avoid overwriting it in lower layers.

## 18. Context in flatMap and Nested Publishers

Reactor operators chained within the same subscription can access the subscriber's Context:

~~~java
return orderRepository.findById(orderId)
        .flatMap(order ->
                Mono.deferContextual(context -> {
                    String id = context.getOrDefault(
                            CorrelationIdWebFilter.CONTEXT_KEY,
                            "unknown"
                    );

                    log.info(
                            "Loading customer for order, correlationId={}",
                            id
                    );

                    return customerRepository.findById(order.customerId())
                            .map(customer -> toResponse(order, customer));
                })
        );
~~~

Context is readable inside the inner publisher because it belongs to the same subscription chain. There is no need to pass the correlation ID via static fields or `ThreadLocal`.

If an inner publisher is subscribed to independently via `subscribe()`, it does not automatically inherit the parent subscription's Context. Avoid manual `subscribe()` inside services; return publishers and compose with `flatMap`, `concatMap`, `then`, or appropriate operators.

## 19. Context Does Not Automatically Propagate to CompletableFuture or Raw Threads

Reactor Context is only guaranteed across publishers composed under Reactor semantics. When crossing into:

- `new Thread(...)`.
- `CompletableFuture.supplyAsync(...)`.
- An Executor without context propagation integration.
- Non-reactive library callbacks.

metadata will not appear there automatically.

When integrating imperative APIs, use Micrometer Context Propagation and an appropriate executor/task decorator, or pass metadata explicitly as arguments. Do not rely on a current `ThreadLocal` still being populated on the worker thread.

Conceptual example with a context-aware executor wrapper:

~~~java
// Pseudocode: how to wrap an Executor depends on Micrometer/Spring version.
Executor contextAwareExecutor =
        ContextExecutorService.wrap(delegateExecutor, contextSnapshotFactory);
~~~

Exact API names and snapshot creation depend on your Micrometer Context Propagation version. When no integration exists, passing the correlation ID explicitly is simple and easy to reason about.

## 20. Correlation IDs in Structured Logs

Key/value logs are easier to search than unstructured plain text:

~~~text
timestamp=2026-11-15T10:00:00Z
level=INFO
service=order-service
correlationId=req-7f2a
traceId=4bf92f3577b34da6a3ce929d0e0e4736
spanId=00f067aa0ba902b7
operation=createOrder
orderId=9001
message="Order saved"
~~~

When using Logback MDC, you can configure a pattern containing `%X{correlationId}`:

~~~xml
<pattern>%d %-5level [%X{correlationId}] %logger - %msg%n</pattern>
~~~

The pattern only prints a value if MDC was bridged/populated when the log event ran. Adding the pattern alone does not read Reactor Context.

Structured logging can use a JSON encoder and emit `correlationId`/`traceId` as dedicated fields. Never use high-cardinality IDs as metric labels; correlation IDs belong in log and trace lookups.

## 21. Propagating Correlation IDs to R2DBC / Database Logs

A correlation ID in Reactor Context does not automatically become an SQL comment, session variable, or field in database server logs. To link application logs with the database, you have several options:

- Use distributed tracing instrumentation for R2DBC/drivers if your stack supports it.
- Record query spans with trace ID and database operation metadata.
- Use database session/application name properties if the driver/database supports setting them safely per connection.
- Use a supported tracing proxy or query instrumentation.

Never append client correlation IDs into SQL text via string concatenation. Doing so hurts query plan caching, introduces injection risks, and pollutes SQL logs with untrusted input.

If using session variables, remember connections are reused in a pool. Values must be set and reset properly before returning a connection to the pool; otherwise, subsequent requests can inherit metadata from previous requests. Prefer official instrumentation mechanisms and test against a real pool.

## 22. Correlation IDs Are Not Authorization or Tenant Isolation

A correlation ID is observability metadata. Never use it to:

- Identify an authenticated user.
- Grant access to resources.
- Select a tenant database without verifying tenant authorization.
- Serve as a unique business idempotency key unless designed with proper semantics.
- Prove a request originated from a trusted service.

If Context carries a tenant ID or security principal, that value must come from a trusted authentication/authorization mechanism. Never trust a client-supplied `X-Tenant-ID` header without verifying access permissions.

Correlation IDs may be supplied by clients to assist technical support, but the server must validate them and may replace them with internal IDs. They must never be used as secrets.

## 23. Context and Concurrent Requests

A major advantage of Reactor Context is that each subscription maintains isolated metadata. Example:

~~~java
Mono<String> readId = Mono.deferContextual(context ->
        Mono.just(context.get(CorrelationIdWebFilter.CONTEXT_KEY))
);

Mono<String> first = readId.contextWrite(context ->
        context.put(CorrelationIdWebFilter.CONTEXT_KEY, "request-A")
);

Mono<String> second = readId.contextWrite(context ->
        context.put(CorrelationIdWebFilter.CONTEXT_KEY, "request-B")
);

return Mono.zip(first, second);
~~~

Both publishers can execute concurrently without overwriting each other's correlation IDs. This differs sharply from a mutable static field or misused `ThreadLocal`.

Never store a request ID in a mutable field on a singleton service:

~~~java
// Unsafe for concurrent requests.
private String currentCorrelationId;
~~~

A singleton service is shared across many requests. One request will overwrite another request's value.

## 24. Handling Internal Requests Without a WebFilter

Some publishers are triggered by schedulers, message listeners, or tests rather than passing through an HTTP `WebFilter`. In those cases, no HTTP-derived correlation ID exists.

Choose a clear policy:

- Generate a workflow ID at the consumer boundary.
- Use a message ID as the correlation key when appropriate.
- Pass an ID from the scheduled job or batch execution.
- Use a fallback value strictly for logs if an ID is optional.

Do not assume every reactive publisher originates from an HTTP request. Each entry point should have a component responsible for creating or extracting the appropriate metadata.

## 25. Correlation IDs Across Message Brokers

When publishing messages, you can include the correlation ID in message headers or event metadata:

~~~java
Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader("correlationId", correlationId)
        .build();
~~~

This example uses the Spring Messaging abstraction; actual header sending depends on the broker binder/producer API.

The consumer reads the header and places the ID into the processing pipeline's Reactor Context:

~~~java
public Mono<Void> handle(
        OrderCreated event,
        String correlationId) {

    return process(event)
            .contextWrite(context ->
                    context.put(
                            CorrelationIdWebFilter.CONTEXT_KEY,
                            correlationId
                    )
            );
}
~~~

When using distributed tracing, broker instrumentation can propagate trace context using the tracing system's standard headers. Do not pass only a correlation ID and drop `traceparent` if you need to stitch distributed traces across messaging.

## 26. Testing Reactor Context with StepVerifier

You can verify that a publisher sees the expected Context value:

~~~java
Mono<String> publisher = Mono.deferContextual(context ->
        Mono.just(context.get("test.correlationId"))
);

StepVerifier.create(
                publisher.contextWrite(context ->
                        context.put("test.correlationId", "test-123")
                )
        )
        .expectAccessibleContext()
        .contains("test.correlationId", "test-123")
        .then()
        .expectNext("test-123")
        .verifyComplete();
~~~

This test confirms Context is written and read within the same subscription. It does not prove MDC or a trace backend is configured properly.

## 27. Testing WebFilter with WebTestClient

Verify a request missing the correlation header:

~~~java
webTestClient.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().exists("X-Correlation-ID");
~~~

Verify a valid header is preserved:

~~~java
webTestClient.get()
        .uri("/api/orders/42")
        .header("X-Correlation-ID", "test-request-42")
        .exchange()
        .expectHeader()
        .valueEquals("X-Correlation-ID", "test-request-42");
~~~

Verify an invalid header is rejected/replaced:

~~~java
webTestClient.get()
        .uri("/api/orders/42")
        .header("X-Correlation-ID", "bad value\nfor-log")
        .exchange()
        .expectHeader()
        .valueMatches(
                "X-Correlation-ID",
                "[A-Za-z0-9._-]{1,128}"
        );
~~~

In real tests, endpoints may require authentication or test fixtures. Also verify that services and HTTP clients receive the expected Context ID, not only that the response header is echoed.

## 28. Testing Against Context Leakage Between Requests

Send multiple concurrent requests with distinct correlation IDs and verify:

- Each response returns the matching ID for that request.
- Logs from request A never contain request B's ID.
- `WebClient` calls from A send ID A.
- Inner publishers within the same request retain the right Context.
- Requests without an ID receive a generated value.

A test using two independent publishers can verify Context isolation:

~~~java
Mono<String> currentId = Mono.deferContextual(context ->
        Mono.just(context.get("correlationId"))
);

Mono<String> requestA = currentId.contextWrite(context ->
        context.put("correlationId", "A")
);

Mono<String> requestB = currentId.contextWrite(context ->
        context.put("correlationId", "B")
);

StepVerifier.create(Mono.zip(requestA, requestB))
        .assertNext(tuple -> {
            assertEquals("A", tuple.getT1());
            assertEquals("B", tuple.getT2());
        })
        .verifyComplete();
~~~

## 29. Common Pitfalls

1. **Setting MDC only at request start.** Callbacks may run on different threads and miss the value.
2. **Using `ThreadLocal` as the primary context store in reactive flows.** Threads do not represent subscriptions.
3. **Calling `subscribe()` to read Context inside a callback.** Creates a detached subscription and loses the parent flow's context.
4. **Replacing all of Reactor Context with `Context.of(...)`.** Can wipe out transaction/security/observation contexts.
5. **Placing `contextWrite` without understanding scope.** Upstream operators may not see the intended value.
6. **Storing request IDs in a mutable singleton field.** Concurrent requests will overwrite each other.
7. **Forgetting to clear MDC after logging.** Thread pools can leak IDs into subsequent requests.
8. **Generating custom trace IDs and overwriting `traceparent`.** Breaks distributed traces or span hierarchies.
9. **Accepting unbounded correlation IDs from clients.** Risks log injection or oversized logs/headers.
10. **Treating correlation IDs as authentication credentials.** IDs are strictly for observability, not authorization.
11. **Assuming R2DBC server logs automatically receive correlation IDs.** Requires instrumentation or database-specific setup.
12. **Assuming Context automatically enters `CompletableFuture`/raw threads.** Requires context propagation or explicit parameters.
13. **Enabling automatic propagation without checking overhead/versions.** APIs and behavior depend on Reactor/Micrometer versions.
14. **Propagating sensitive metadata to all external services.** Forward only needed fields to trusted dependencies.

## Quick Selection Rules

- Use Reactor Context for metadata flowing across a reactive subscription.
- Create/validate correlation IDs in a `WebFilter` or corresponding entry point.
- Use `contextWrite(context -> context.put(...))` to add keys while preserving the existing Context.
- Use `deferContextual` to read values at subscription time.
- Never use `ThreadLocal`/MDC as the source of truth for reactive flows.
- Use an MDC bridge or Micrometer Context Propagation when automatic logging across threads is needed.
- Let Micrometer Tracing/OpenTelemetry manage trace IDs, span IDs, and W3C trace headers.
- Propagate correlation IDs over `WebClient`/message headers only to trusted dependencies.
- Never call detached `subscribe()` to read Context; chain publishers onto the active pipeline.
- Keep correlation metadata separate from authorization and business data.
- Test Context, `WebFilter`, MDC propagation, and concurrent requests.

Reactor Context is the right mechanism for passing correlation metadata through WebFlux and Spring Data R2DBC applications because it binds to subscriptions rather than threads. Create or validate the correlation ID at the entry point, add it via `contextWrite`, read it via `deferContextual`, and preserve the existing Context so transaction, security, and tracing metadata remain intact. When pushing values into MDC or imperative code, use Micrometer Context Propagation or a bridge with proper cleanup. For distributed tracing, let the tracing library manage trace/span IDs and W3C headers; correlation IDs serve strictly as log correlation keys. This approach tracks requests across reactive layers without relying on thread affinity or leaking metadata between concurrent requests.
