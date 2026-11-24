# Propagating Correlation IDs and Request Metadata with Reactor Context

## 1. Why Does a WebFlux Application Need Reactor Context?

In Spring WebFlux, an HTTP request can pass through a `WebFilter`, controller, service, database, `WebClient`, and many Reactor operators. Along the way, callbacks do not necessarily run on the same thread. If you use `ThreadLocal` or SLF4J MDC manually to hold a **correlation ID**, a callback running after **`publishOn`**, **`subscribeOn`**, or asynchronous I/O may fail to see the initial metadata.

**Reactor Context** is a **per-subscription** metadata propagation mechanism that lets components in the same reactive chain read the correlation ID and request metadata without adding parameters to every method.

For example, an HTTP request carries the code **`REQ-2026-A`**, passes through a handler that fetches order details, calls a shipping service, and logs an error. We want logs at every layer to carry the same ID so all related events are easy to find. Reactor Context lets you attach the ID at an intentional boundary and read it back in operators within the right scope.

This lesson helps you:

- Understand **`Context`**, **`ContextView`**, **`contextWrite`**, and **`deferContextual`**.
- Explain how Context flows from **downstream to upstream** upon subscription.
- Propagate a correlation ID across services, nested Publishers, schedulers, and asynchronous pipelines.
- Generate the ID in a **`WebFilter`**, read it in a service, and attach it to **`WebClient` outbound headers**.
- Distinguish Reactor Context from **`ThreadLocal`**, **`MDC`**, Micrometer Context Propagation, and distributed tracing.
- Design safe metadata, test isolation across requests, and avoid losing Context due to manual subscriptions.

## 2. Context Is Subscription Data, Not Thread Data

Key concepts:

| Component | Purpose |
| --- | --- |
| **`reactor.util.context.Context`** | Structurally immutable key–value map bound to the Subscriber |
| **`ContextView`** | Read-only interface; used to access metadata from the pipeline |
| **`contextWrite(ContextView)`** | Merges a `ContextView` into the downstream Subscriber's Context and produces a new Context for upstream |
| **`contextWrite(Function<Context,Context>)`** | Transforms the existing Context, typically using **`ctx.put(key,value)`** |
| **`Mono.deferContextual`** | Creates a `Mono` at subscribe time with read access to the current `ContextView` |
| **`Flux.deferContextual`** | Same for `Flux` |
| **`transformDeferredContextual`** | Uses `ContextView` when transforming a pipeline at subscription time |
| **`Signal.getContextView()`** | Reads Context when observing signals via suitable operators like `doOnEach` |

**Immutable Context:** **`ctx.put(KEY, value)`** returns a new Context; it does not mutate the previous `ctx` object. However, if the value is a mutable object, that object's fields can still be modified. Therefore, keep Context values small and immutable.

**Each subscriber has its own Context:** the same predefined `Mono` can be subscribed to multiple times with different correlation IDs. This prevents metadata from mixing between two HTTP requests, provided the application does not use an external mutable `static` variable to hold the ID.

**Thread-independent:** Context is metadata on the subscription relationship and is propagated through Reactor operators. Switching threads with **`publishOn`** does not drop Reactor Context, though it can lose unbridged `ThreadLocal` data.

**Does not automatically cross process boundaries:** Reactor Context in service A does not travel automatically to service B over the network. To correlate requests across services, propagate the correlation ID via HTTP headers, message metadata, or a configured tracing mechanism.

## 3. Context Propagation Direction and `contextWrite` Placement

Data flows from upstream → downstream. Subscription initialization, including Context propagation, flows in the opposite direction: from downstream → upstream.

~~~text
                  onNext / onError / onComplete ↓

Mono.deferContextual(view -> ...)
            │
        .map(...)
            │
      .flatMap(...)
            │
.contextWrite(ctx -> ctx.put(KEY, "REQ-101"))
            │
          Subscriber

                  subscription / Context ↑
~~~

Therefore, the following is valid:

~~~java
Mono<String> result = Mono.deferContextual(view ->
        Mono.just("cid=" + view.get("cid"))
    )
    .contextWrite(ctx -> ctx.put("cid", "REQ-101"));
~~~

Result after subscribing:

~~~text
cid=REQ-101
~~~

Conversely, the placement below prevents the reader from seeing the value just written:

~~~java
Mono<String> result = Mono.just("item")
    .contextWrite(ctx -> ctx.put("cid", "REQ-101"))
    .flatMap(item -> Mono.deferContextual(view ->
        Mono.just(view.getOrDefault("cid", "MISSING"))
    ));
~~~

The **`flatMap`** operator sits downstream of that `contextWrite`. Because Context travels from downstream to upstream, the new Context affects only **`Mono.just("item")`** above it. `flatMap` reads the Context of its own downstream branch, producing **`MISSING`**.

**Rule to remember:** **`contextWrite` is normally placed below the site that needs to read it in the chain expression**. It affects **upstream** operators; it does not emit a metadata value downward along `onNext`.

### 3.1. Two Writes to the Same Key

~~~java
Mono<String> result = Mono.deferContextual(view ->
        Mono.just(view.get("cid"))
    )
    .contextWrite(ctx -> ctx.put("cid", "INNER"))
    .contextWrite(ctx -> ctx.put("cid", "OUTER"));
~~~

The result is **`INNER`**. As subscription travels upward, `OUTER` is written first, then the `contextWrite` closer to the reader creates a Context with `INNER`. Have **a consistent policy** so inner services do not accidentally overwrite the request's correlation ID.

### 3.2. Child Branch Context Is Isolated

~~~java
Mono<String> result = Mono.just("A")
    .flatMap(value ->
        Mono.deferContextual(view ->
            Mono.just(value + view.getOrDefault("cid", "?"))
        )
        .contextWrite(ctx -> ctx.put("cid", "INNER"))
    )
    .flatMap(value ->
        Mono.deferContextual(view ->
            Mono.just(value + view.getOrDefault("cid", "?"))
        )
    );
~~~

The first `flatMap` branch sees `INNER`; the next branch does not automatically inherit the previous branch's local write. With no `cid` in the outer Context, the result is **`AINNER?`**. Local Context inside an inner Publisher does not alter the Context of outer branches.

## 4. Reading Context Safely and Organizing Keys

A component may be invoked by an HTTP request or by a job with no HTTP context. When a key is optional, use **`getOrDefault`**:

~~~java
Mono<String> readCid = Mono.deferContextual(view -> {
    String cid = view.getOrDefault("app.correlationId", "unknown");
    return Mono.just("cid=" + cid);
});
~~~

Reading methods:

- **`view.get(key)`**: retrieves the value if the key is present; throws an error if missing.
- **`view.getOrDefault(key, defaultValue)`**: returns the default when the key is missing.
- **`view.hasKey(key)`**: checks whether the key is present.
- **`view.getOrEmpty(key)`**: returns an `Optional` for values that may be absent.
- **`Context.of(...)`**: creates a Context with a small set of key–value pairs.
- **`Context.empty()`**: creates an empty Context.
- **`ctx.put(key,value)`** and **`ctx.delete(key)`**: return a new Context without modifying in place.

Context does not accept `null` keys or values. Never use `null` to represent "no request yet."

### Shared Keys

String keys can easily collide across libraries or modules. You can use a centrally defined enum or object:

~~~java
public enum RequestContextKey {
    CORRELATION_ID,
    REQUEST_METHOD
}
~~~

Writers and readers must use **the exact same key**, never creating separate `Object` instances even if their display names match. Never overwrite Spring Security or tracing keys unless you understand their contracts.

### What Data Should Be Stored?

Reasonable: correlation ID, request ID, HTTP method, locale code, normalized route template, small immutable metadata. If multiple related fields are needed, consider an immutable **`record`**.

Should not be placed into Context: raw `Authorization` headers, passwords, access tokens, request bodies, the entire `ServerWebExchange`, unnecessary personal data, large objects, or shared mutable state. Context is a metadata propagation mechanism, not a place for durable business state.

**A correlation ID does not prove identity.** Client-supplied values can be forged. Never use it as a basis for granting permissions or determining tenants. Use official authentication and security context systems for security purposes.

## 5. Java 17+: Runnable Maven Example

The following program uses **Reactor Core 3.6.6** and demonstrates the key points: per-subscription Context, `contextWrite` precedence, values after `publishOn`, missing keys, and nested Publishers. The output is designed not to depend on thread names or scheduler timing.

Create the layout:

~~~text
reactor-context-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── ReactorContextDemo.java
~~~

File **`pom.xml`**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>reactor-context-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core</artifactId>
      <version>3.6.6</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

File **`src/main/java/ReactorContextDemo.java`**:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.util.context.Context;

public class ReactorContextDemo {

    enum Key {
        CORRELATION_ID,
        REQUEST
    }

    static Mono<String> describe() {
        return Mono.deferContextual(view ->
            Mono.just(
                "cid=" + view.getOrDefault(Key.CORRELATION_ID, "none")
                + "; request=" + view.getOrDefault(Key.REQUEST, "none")
            )
        );
    }

    public static void main(String[] args) {
        System.out.println("=== 1. Two subscriptions ===");

        Mono<String> definition = describe();

        System.out.println(
            definition.contextWrite(
                Context.of(
                    Key.CORRELATION_ID, "CID-A",
                    Key.REQUEST, "GET /orders"
                )
            ).block()
        );

        System.out.println(
            definition.contextWrite(
                Context.of(
                    Key.CORRELATION_ID, "CID-B",
                    Key.REQUEST, "POST /orders"
                )
            ).block()
        );

        System.out.println("=== 2. Position ===");

        System.out.println(
            Mono.deferContextual(view ->
                    Mono.just(
                        "closest=" + view.getOrDefault(
                            Key.CORRELATION_ID, "missing"
                        )
                    )
                )
                .contextWrite(ctx ->
                    ctx.put(Key.CORRELATION_ID, "INNER")
                )
                .contextWrite(ctx ->
                    ctx.put(Key.CORRELATION_ID, "OUTER")
                )
                .block()
        );

        System.out.println(
            Mono.just("value")
                .contextWrite(ctx ->
                    ctx.put(Key.CORRELATION_ID, "TOO-HIGH")
                )
                .flatMap(value ->
                    Mono.deferContextual(view ->
                        Mono.just(
                            "downstream=" + view.getOrDefault(
                                Key.CORRELATION_ID, "missing"
                            )
                        )
                    )
                )
                .block()
        );

        System.out.println("=== 3. Scheduler ===");

        System.out.println(
            Mono.just("order-7")
                .publishOn(Schedulers.parallel())
                .flatMap(order ->
                    Mono.deferContextual(view ->
                        Mono.just(
                            order + " cid=" + view.getOrDefault(
                                Key.CORRELATION_ID, "missing"
                            )
                        )
                    )
                )
                .contextWrite(ctx ->
                    ctx.put(Key.CORRELATION_ID, "CID-HOP")
                )
                .block()
        );

        System.out.println("=== 4. Missing context ===");
        System.out.println(describe().block());

        System.out.println("=== 5. Inner publishers ===");

        Flux.just("A", "B")
            .concatMap(item ->
                Mono.deferContextual(view ->
                    Mono.just(
                        item + ":" + view.getOrDefault(
                            Key.CORRELATION_ID, "missing"
                        )
                    )
                )
            )
            .contextWrite(ctx ->
                ctx.put(Key.CORRELATION_ID, "CID-LIST")
            )
            .doOnNext(System.out::println)
            .blockLast();
    }
}
~~~

In the directory containing **`pom.xml`**, requiring JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=ReactorContextDemo
~~~

Expected stdout:

~~~text
=== 1. Two subscriptions ===
cid=CID-A; request=GET /orders
cid=CID-B; request=POST /orders
=== 2. Position ===
closest=INNER
downstream=missing
=== 3. Scheduler ===
order-7 cid=CID-HOP
=== 4. Missing context ===
cid=none; request=none
=== 5. Inner publishers ===
A:CID-LIST
B:CID-LIST
~~~

Reading the example:

1. **Two subscriptions:** One `Mono` definition is reused while Context is supplied separately per subscription. No ID from request A is kept in a static variable for request B to misread.
2. **Position:** The operator closer to the reader writes `INNER`, so the result is `INNER`. The `TOO-HIGH` write sits upstream of the `flatMap` reading the key, so downstream receives `missing`.
3. **Scheduler:** After `publishOn`, `Mono.deferContextual` still receives `CID-HOP`; Context travels with the subscription, independent of staying on the same thread.
4. **Missing context:** When the key is absent, `getOrDefault` produces a safe value.
5. **Inner publishers:** The `Mono` created inside `concatMap` is a nested Publisher; it reads the parent chain's Context and emits data carrying `CID-LIST`. `concatMap` preserves the order `A, B`.

**`block()`** and **`blockLast()`** are solely for waiting in the CLI; in a WebFlux controller, return `Mono`/`Flux` and let the framework subscribe without blocking the event loop.

## 6. Generating Correlation IDs in a `WebFilter`

**`WebFilter`** sits at the HTTP boundary in Spring WebFlux. It can read an incoming header, normalize the ID, add the header to the response, and inject metadata into Reactor Context for the entire request-handling chain.

An illustrative policy:

- Accept **`X-Correlation-ID`** with length 1 to 64, consisting only of letters, digits, underscores, hyphens, or dots.
- If missing or invalid, generate a new UUID.
- Never use a client-supplied header to make authorization decisions.
- Keep the same ID across the request's processing layers.
- Avoid logging raw paths/queries or sensitive details.

Using the `RequestContextKey` enum from section 4. This is a **snippet from a Spring WebFlux application**:

~~~java
@Component
public class CorrelationIdFilter implements WebFilter {
    private static final String HEADER = "X-Correlation-ID";

    @Override
    public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    ) {
        String incoming = exchange.getRequest()
            .getHeaders()
            .getFirst(HEADER);

        String cid = incoming != null
            && incoming.matches("[A-Za-z0-9._-]{1,64}")
                ? incoming
                : UUID.randomUUID().toString();

        exchange.getResponse().getHeaders().set(HEADER, cid);

        String method = exchange.getRequest()
            .getMethod()
            .name();

        return chain.filter(exchange)
            .contextWrite(ctx ->
                ctx.put(RequestContextKey.CORRELATION_ID, cid)
                   .put(RequestContextKey.REQUEST_METHOD, method)
            );
    }
}
~~~

This section assumes the enum is named:

~~~java
public enum RequestContextKey {
    CORRELATION_ID,
    REQUEST_METHOD
}
~~~

Main imports: **`java.util.UUID`**, **`org.springframework.stereotype.Component`**, **`org.springframework.web.server.WebFilter`**, **`WebFilterChain`**, **`ServerWebExchange`**, **`reactor.core.publisher.Mono`**.

**Why is `contextWrite` placed after `chain.filter(exchange)`?** In the return expression, `chain.filter` is the upstream Publisher; placing `contextWrite` below it puts Context onto the subscription path when the framework executes the chain. If metadata is attached to a separate `Mono` that does not wrap the HTTP pipeline, the service will not be able to read it.

The response header lets clients quote the ID when requesting support. In systems with proxies/gateways, agree on trust policies, size limits, and avoid overloading the same header with conflicting meanings.

## 7. Reading Metadata in a Service and Logging

Suppose a reactive repository returns `Mono<Order>`. The service can read Context and pass `cid` directly into logger calls:

~~~java
@Service
public class OrderService {
    private final OrderRepository repository;
    private final Logger log =
        LoggerFactory.getLogger(OrderService.class);

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public Mono<Order> findById(String orderId) {
        return Mono.deferContextual(view -> {
            String cid = view.getOrDefault(
                RequestContextKey.CORRELATION_ID,
                "unknown"
            );

            return repository.findById(orderId)
                .doOnNext(order ->
                    log.info("cid={} order fetched", cid)
                )
                .doOnError(error ->
                    log.warn("cid={} order lookup failed", cid, error)
                );
        });
    }
}
~~~

This snippet belongs in a Spring project with **`Order`**, **`OrderRepository`**, and an appropriate SLF4J logger. **No MDC is required** for `cid` to appear in the logs because it is passed explicitly as an argument.

Controller:

~~~java
@GetMapping("/orders/{id}")
public Mono<Order> getOrder(@PathVariable String id) {
    return orderService.findById(id);
}
~~~

Spring WebFlux subscribes to the returned `Mono` during HTTP handling. The service's operators see Context if it was attached at the proper `WebFilter` boundary. Never call **`subscribe()`** manually inside a controller just to kick off work: it creates a separate subscription that is hard to tie to HTTP request cancellation/errors and may not inherit the current Context.

### Logging per Signal

In some cases you may want to observe individual signals with **`doOnEach`**:

~~~java
Flux<Order> data = repository.findAll()
    .doOnEach(signal -> {
        if (signal.isOnNext()) {
            String cid = signal.getContextView()
                .getOrDefault(
                    RequestContextKey.CORRELATION_ID,
                    "unknown"
                );
            log.info("cid={} order emitted", cid);
        }
    });
~~~

A **`Signal`** can be `onNext`, `onError`, or `onComplete`; check **`isOnNext()`** before relying on element data. **`doOnEach`** sits within the Context scope upstream of the corresponding `contextWrite`. Logging callbacks should avoid logging sensitive full payloads.

## 8. Propagating the ID via `WebClient` to Another Service

Reactor Context does not cross the network by itself. If a request in service A calls service B, you must add the correlation ID to an outbound header or let configured distributed tracing handle propagation.

A `WebClient` filter can read Context at subscription time:

~~~java
@Bean
WebClient downstreamClient(WebClient.Builder builder) {
    return builder
        .filter((request, next) ->
            Mono.deferContextual(view -> {
                String cid = view.getOrDefault(
                    RequestContextKey.CORRELATION_ID,
                    ""
                );

                ClientRequest.Builder outbound =
                    ClientRequest.from(request);

                if (!cid.isBlank()) {
                    outbound.headers(headers ->
                        headers.set("X-Correlation-ID", cid)
                    );
                }

                return next.exchange(outbound.build());
            })
        )
        .build();
}
~~~

Main imports: **`WebClient`**, **`ClientRequest`**, **`Mono`**, **`@Bean`**, and `RequestContextKey`. The snippet sits inside an appropriate configuration class.

**`Mono.deferContextual`** ensures Context is read when subscribing to the outbound request. **`next.exchange`** continues the `WebClient` filter chain. The header is set explicitly at the HTTP boundary; service B must read, validate, and place it into a new Reactor Context for the incoming request it receives.

**Do not use correlation IDs in place of trace/span IDs.** With Micrometer Tracing/OpenTelemetry, **`traceparent`/`tracestate`** headers and span context have dedicated semantics. If a tracing library manages those headers, do not overwrite them with business IDs. An application can maintain a separate correlation ID for lookup while keeping trace/span managed by instrumentation.

For brokers or background jobs, the same principle applies: put the ID into **message metadata** when sending and reconstruct Context for the consumer's subscription per system policy. The producer's Reactor Context does not travel automatically across another process.

## 9. `ThreadLocal`, MDC, and Micrometer Context Propagation

| Criterion | Reactor Context | Traditional `ThreadLocal`/MDC |
| --- | --- | --- |
| Bound to | Subscriber / subscription | Running thread |
| Read via | **`deferContextual`**, **`ContextView`** | **`ThreadLocal.get`**, **`MDC.get`** |
| Write via | **`contextWrite`** | **`ThreadLocal.set`**, **`MDC.put`** |
| Across `publishOn` | Context remains available inside the Reactor pipeline | Does not automatically transfer values to the new thread |
| Lifecycle management | Per subscription and operator scope | Requires per-thread restore/clear |
| Across network | Does not propagate automatically | Also does not propagate automatically |

Risk example:

~~~java
MDC.put("correlationId", cid);

return service.find()
    .publishOn(Schedulers.parallel())
    .doOnNext(value -> log.info("done"));
~~~

Here MDC is written on the initial thread, while the logging callback may run on a different scheduler. Without bridge configuration, there is no guarantee the log will have `cid`. If MDC is not cleared in time, a reused thread even risks carrying data from another request.

**Most reliable approach when only a few logs need it:** read Reactor Context via `deferContextual` and pass `cid` directly as a log argument as shown in section 7.

### Can Context Automatically Sync with MDC?

Reactor 3.5+ supports integration with **`io.micrometer:context-propagation`** when the dependency is present. Distinguish two modes:

- **Default/limited mode**: supports restoring `ThreadLocal` across certain operators and mechanisms, such as `handle` or `tap`, per the integration contract.
- **Automatic mode**: can enable **`Hooks.enableAutomaticContextPropagation()`** at application startup. This uses registered **`ThreadLocalAccessor`** instances matching the keys to restore/clear `ThreadLocal` when executing new subscriptions.

**Simply calling `contextWrite` does not make MDC appear on every thread.** You need the propagation library, accessors, tracing/observation configuration, and proper lifecycle. A Spring Boot application may pre-configure part of this, so verify in practice. If your system already uses a tracing framework, let it manage MDC and trace context rather than enabling multiple inconsistent bridges.

## 10. Boundaries Where Context Can Be Lost

### 10.1. Subscribing Manually in Application Code

~~~java
// Avoid: detached second subscription.
return Mono.deferContextual(view -> {
    String cid = view.get("cid");
    asynchronousSideEffect().subscribe();
    return Mono.just(cid);
});
~~~

The subscription to `asynchronousSideEffect` **does not automatically inherit the parent Context**, and its errors/cancellation may not attach to the HTTP request. Compose it into the same pipeline:

~~~java
return Mono.deferContextual(view ->
    asynchronousSideEffect()
        .thenReturn(view.get("cid"))
);
~~~

This snippet assumes `asynchronousSideEffect` returns `Mono<Void>` or a suitable Publisher. The work is **awaited in the same flow**, and Reactor manages errors and cancellation together.

If you genuinely need fire-and-forget, design an independent job with lifecycle ownership, logging/error handling, and an **explicitly passed** correlation ID, rather than relying on a `subscribe()` inside a request callback.

### 10.2. `CompletableFuture` and Manually Created Threads

**`CompletableFuture.supplyAsync`** or **`ExecutorService`** does not automatically carry the caller's Reactor Context. You can read Context on the Reactor side and pass the needed data to the external API:

~~~java
Mono<Result> result = Mono.deferContextual(view -> {
    String cid = view.getOrDefault("cid", "unknown");

    return Mono.fromFuture(
        startExternalCall(cid)
    );
});
~~~

This snippet assumes a `Result` type and a `startExternalCall` method that accepts `cid` and returns `CompletableFuture<Result>`. Passing parameters explicitly keeps non-Reactor code from assuming Context exists on its thread.

### 10.3. Overrides in Inner Publishers

A `contextWrite` inside a `flatMap` branch can affect that inner Publisher without affecting sibling branches or outer downstream operators. If correlation IDs differ across branches, check whether some code explicitly calls `put` on the same key.

### 10.4. Third-Party Publishers

Reactor Context is specific to Reactor and operators that support it. A library implementing only basic Reactive Streams is not required to provide the same Context behavior inside its own code. If metadata is needed at that boundary, check the integration contract or pass it explicitly.

## 11. Testing and Verification

For correlation IDs, test at a minimum: reading properly when the key exists, handling when the key is missing, and verifying two independent subscriptions do not swap metadata.

In a test project with **`reactor-test`** and JUnit:

~~~java
@Test
void correlationIdIsVisible() {
    Mono<String> value = Mono.deferContextual(view ->
        Mono.just(view.getOrDefault("cid", "missing"))
    );

    StepVerifier.create(
            value.contextWrite(Context.of("cid", "CID-TEST"))
        )
        .expectNext("CID-TEST")
        .verifyComplete();
}
~~~

This is a test snippet (not part of section 5's main class). It requires **`io.projectreactor:reactor-test`** compatible with `reactor-core` and JUnit Jupiter.

Missing-key case:

~~~java
StepVerifier.create(
        Mono.deferContextual(view ->
            Mono.just(view.getOrDefault("cid", "missing"))
        )
    )
    .expectNext("missing")
    .verifyComplete();
~~~

With WebFlux, **`WebTestClient`** can send an **`X-Correlation-ID`** header, assert the normalized response header, and verify the service reads the right Context during an actual request. Testing an isolated service with `contextWrite` alone is not enough to prove the `WebFilter` attaches Context at the right spot in the HTTP chain.

For MDC/automatic context propagation, run tests with actual accessor/hook configuration enabled. Global hooks affect other subscriptions; tests must manage state reset/restoration to avoid cross-test interference.

## 12. Debugging When Correlation ID Disappears

If service logs print **`unknown`** or **`missing`**, check in order:

1. **Did the `WebFilter` run for this endpoint?** Was the ID taken from a header or generated as a UUID?
2. **Is `contextWrite` placed downstream of `chain.filter`?** It must wrap the service portion that needs to read it.
3. **Do all layers use the same key enum/object/string?** Different keys will not match.
4. **Is the reading operator upstream or downstream of `contextWrite`?** Writing Context above the reader in code does not have the intended effect.
5. **Did a manual `subscribe()` start a new stream?** A new stream does not automatically capture Context from the running stream.
6. **Is there a `CompletableFuture` or custom executor callback that needs metadata passed explicitly?**
7. **Is an inner branch overriding the same key?** The operator closer to the read site may determine the final value.
8. **Are you reading Reactor Context or MDC?** An empty MDC on the current thread does not prove Reactor Context is empty.
9. **Was the pipeline actually subscribed to?** `deferContextual` does not run when merely assembling a `Mono`.
10. **Did cancellation/timeout occur before the log callback?** `doOnNext` will not run if no item arrives.

When debugging, add a Context read point right at service entry:

~~~java
return Mono.deferContextual(view -> {
    String cid = view.getOrDefault(
        RequestContextKey.CORRELATION_ID, "MISSING"
    );
    log.debug("cid={} service entry", cid);
    return performOperation();
});
~~~

If the service-entry log has the right `cid` while another callback lacks MDC, the issue is usually `ThreadLocal` bridging. If even the service-entry log lacks the key, focus on the `WebFilter`, `contextWrite` placement, key identity, and subscription boundaries.

## 13. Security and Architectural Choices

Reactor Context helps propagate **metadata**, but it does not replace security, transactions, or distributed tracing.

- **Do not trust arbitrary headers:** validate length/format, and distinguish IDs issued by a trusted gateway from user-supplied IDs.
- **Do not use the ID to authenticate users/tenants:** use Spring Security and `ReactiveSecurityContextHolder` when security context is needed; a correlation ID is a lookup aid.
- **Do not put raw request bodies or tokens into Context:** avoid retaining large references and leaking information in logs.
- **Do not generate a brand-new ID in every service:** if the goal is tracking one request across layers, preserve one consistent ID.
- **Do not log sensitive raw query strings:** use route templates and minimal metadata.
- **Do not confuse correlation with trace/span:** `traceparent` and tracing data have independent propagation mechanisms.
- **Do not treat manual `subscribe()` as a managed child flow:** compose a reactive chain or pass metadata to detached tasks under a separate contract.
- **Do not treat Context as a durable cache:** it lives for the subscription lifecycle.
- **Do not rely on staying on the same thread:** read via `ContextView`, or configure context-propagation per documentation.
- **Watch out for recovered errors:** when `onErrorResume` falls back to a success value, a `doOnError` placed after recovery will not see the original error. Place logging/metrics appropriately to correlate errors with the same correlation ID.

For systems already running Micrometer Tracing, you can use trace/span IDs as the primary correlation mechanism first; add a separate correlation ID only when there is a clear business requirement, and ensure it does not interfere with official header propagation.

## 14. Summary of Request Data Propagation Choices

| Need | Appropriate Approach |
| --- | --- |
| One or two service layers, compiler-checked contract | Explicit method parameters |
| Metadata needed by multiple operators in the same Reactor subscription | **Reactor Context** |
| Logs needing correlation directly without configuring MDC | **`deferContextual`** and logger arguments |
| MDC needing to work across schedulers | **Micrometer Context Propagation** with proper accessors/config |
| Propagating correlation to another HTTP service | **`WebClient` filter** adding headers or tracing instrumentation |
| Propagating to a message consumer | Message headers/metadata, rebuilding Context at consumer |
| Distributed trace analysis across services | Micrometer Tracing/OpenTelemetry and standard propagation |
| Propagating authentication and authorization info | Framework-managed security context mechanism |

## 15. Self-Check

**Q1.** Is Reactor Context bound to a thread or a subscription?  
**Answer:** The Subscription and Subscriber of the Reactor chain.

**Q2.** Why can a `contextWrite` placed at the end of a pipeline still be seen by `deferContextual` above it?  
**Answer:** Context travels with the subscription process from downstream to upstream.

**Q3.** If `deferContextual` sits downstream of `contextWrite`, will it automatically see the key just written by `contextWrite`?  
**Answer:** No. You must account for operator placement and Context propagation direction.

**Q4.** After `publishOn`, do `ThreadLocal` and Reactor Context behave identically?  
**Answer:** No. Reactor Context remains accessible within the same chain; `ThreadLocal` requires bridging/restoration across thread switches.

**Q5.** Does Reactor Context automatically appear in HTTP requests to another service?  
**Answer:** No. You must use headers or propagation instrumentation.

**Q6.** Why shouldn't you call `subscribe` inside a controller to keep a background job running?  
**Answer:** It creates an independent subscription, loses request error/cancellation management, and does not automatically inherit Context.

**Exercise A:** In the Java demo, swap the positions of `INNER` and `OUTER` `contextWrite` calls; predict the output and explain using subscription direction.

**Exercise B:** Create 20 subscriptions of the same `Mono.deferContextual` with 20 distinct `cid` values, process across a scheduler, and verify no request's CID appears in another request's result.

**Exercise C:** Implement a `WebFilter` and `WebClient` filter; use `WebTestClient` with a mock HTTP server to confirm valid incoming `cid` values are forwarded via outbound headers.

**Exercise D:** Inject an error in a service and recover to a cache via `onErrorResume`. Inspect `doOnError` logs before and after recovery; verify both branches still log the same correlation ID.

**Exercise E:** Try reading MDC after `publishOn` without bridge configuration, then enable Micrometer Context Propagation with the matching key accessor. Compare results and confirm `ThreadLocal` is cleared/restored per lifecycle.

## 16. References

- Reactor Reference — Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Reactor Reference — Context-Propagation Support: https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html
- Reactor API — Context: https://projectreactor.io/docs/core/release/api/reactor/util/context/Context.html
- Reactor API — ContextView: https://projectreactor.io/docs/core/release/api/reactor/util/context/ContextView.html
- Spring Framework — WebClient Context: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-context.html
- Spring Framework — WebFilter: https://docs.spring.io/spring-framework/reference/web/webflux/filters.html
- Micrometer — Observation Instrumentation: https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html
- Reactive Streams for the JVM: https://github.com/reactive-streams/reactive-streams-jvm
