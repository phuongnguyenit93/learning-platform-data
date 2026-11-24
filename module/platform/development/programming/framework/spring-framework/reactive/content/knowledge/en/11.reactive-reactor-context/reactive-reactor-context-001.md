# Why ThreadLocal Is Not Enough Across Thread-Switching Chains

In **Spring WebFlux** and **Project Reactor**, request-scoped data — such as `requestId`, `traceId`, audit information, or security context — often has to travel through multiple asynchronous steps. Those steps are **not guaranteed to run on the same Java thread**. Therefore, storing data in a `ThreadLocal` at the start of a request and reading it in every subsequent step is an unsafe assumption.

**`ThreadLocal` binds a value to the current thread; Reactor `Context` binds values to a subscription and propagates context along the subscriber chain.** A single subscription can hop across multiple threads while still accessing its Context through the appropriate APIs. This is why Reactor provides `Context`, `ContextView`, `contextWrite`, and `deferContextual`.

This lesson focuses on **why `ThreadLocal` falls short when a pipeline switches threads**, how Reactor `Context` solves this, and the boundaries you need to understand to apply it correctly in WebFlux.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain accurately where `ThreadLocal` stores values, and why thread pools and event loops make it unreliable for long-lived request context.
2. Identify when a Reactor pipeline can switch threads due to `publishOn`, `subscribeOn`, I/O sources, and asynchronous callbacks.
3. Understand why `Context` is attached to the **Subscriber/Subscription**, is scoped per subscription, and is propagated from downstream to upstream when subscription occurs.
4. Use `contextWrite` to add data, `Mono.deferContextual` or `Flux.deferContextual` to read data, and `ContextView` appropriately.
5. Distinguish Reactor `Context` from `ThreadLocal`, HTTP headers, imperative `SecurityContextHolder`, and Spring's `ApplicationContext`.
6. Use context across `flatMap`, `publishOn`, and WebFlux filters/services without relying on a fixed thread.
7. Understand how Micrometer Context Propagation can support legacy libraries that depend on `ThreadLocal`, while not automatically solving every asynchronous boundary.
8. Test the presence, isolation, and scope of `Context` with `StepVerifier`.

## 2. How Does ThreadLocal Actually Work?

`ThreadLocal<T>` allows the same `ThreadLocal` instance to return **a separate value for each Java thread**:

~~~java
ThreadLocal<String> correlationId = new ThreadLocal<>();

correlationId.set("req-100");
String value = correlationId.get(); // "req-100" on the current thread.
correlationId.remove();            // Remove the value from the current thread.
~~~

This mechanism is useful when the entire unit of work always runs on the same thread and has a clear start and end. For example, an imperative application can put metadata into a `ThreadLocal` in a filter, run synchronous logic on the same request thread, and call `remove()` in a `finally` block.

**However, `ThreadLocal` does not "belong to the request."** It belongs to the **executing thread**. When that thread leaves request A to handle request B, the value attached to A may remain if it is not cleaned up properly. When request A moves to another thread, the new thread does not automatically see the value set on the old thread.

Consider two threads and two requests:

~~~text
Thread event-loop-1:
  Request A: ThreadLocal.set("A")
      |
      +-- Start asynchronous work
      |
      +-- Worker returns to handle Request B

Thread worker-2:
  Work for Request A continues
      |
      +-- ThreadLocal.get() => usually null,
          or a separate value already attached to worker-2

Thread event-loop-1:
  Later receives an event for Request C
      |
      +-- If remove() was forgotten, value "A" may still be here
~~~

This is a **risk diagram**; not every system will leak context. If a library or framework sets up proper capture/restore/cleanup mechanisms, `ThreadLocal` can be restored at certain points. However, manual `set/get` alone **does not create that mechanism**.

### Why Isn't InheritableThreadLocal a General Solution Either?

`InheritableThreadLocal` supports copying values when **creating a child thread**, which does not mean it understands tasks submitted to an already running thread pool. Event-loop workers and scheduler workers are typically reused across many requests. Therefore, it does not properly solve per-subscription scoping and can even increase the risk of incorrect context if applied without control.

## 3. Why Isn't a Reactor Pipeline Bound to One Thread?

`Mono` and `Flux` describe the emission and transformation of signals. Creating a `Mono` or `Flux` itself does not necessarily create a thread; however, the source publisher, schedulers, and asynchronous boundaries can change where callbacks run.

For example:

~~~java
Mono<String> pipeline = Mono.just("start")
    .map(value -> value + "-mapped")
    .publishOn(Schedulers.parallel())
    .map(value -> value + "-processed");
~~~

This is an **integration snippet**; it requires importing `reactor.core.publisher.Mono` and `reactor.core.scheduler.Schedulers`. `publishOn` switches the processing of signals after it to a worker of the chosen scheduler. If code calls `ThreadLocal.set(...)` before the boundary, the callback after `publishOn` typically runs on a different worker and will not see the value set on the old thread.

`subscribeOn(scheduler)`, on the other hand, affects the subscription process and how the upstream source executes. For instance, `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` is commonly used to isolate synchronous/blocking calls from the event loop.

In WebFlux, thread-switching boundaries can also come from:

- Reactor Netty when I/O is ready and signals are emitted on an event-loop worker.
- `publishOn` and `subscribeOn` used by the application or libraries.
- `flatMap` invoking asynchronous publishers, such as WebClient, database drivers, or timers.
- `Mono.delay` emitting signals on a timer scheduler.
- Adapters to `CompletableFuture`, callback-based libraries, or external executors (which require separate consideration for bridging Context).

**Do not assume "one request = one thread" or "one Mono = one thread."** The same request can pass through multiple threads; the same thread can serve different requests over time. Even if a test run happens to use the same thread from start to finish, that is not a general contract of Reactive Streams.

### An Example of Wrong Results When Relying on ThreadLocal

~~~text
T0: event-loop-1 -> request A: ThreadLocal.set("trace-A")
T1: event-loop-1 -> subscribe to WebClient publisher
T2: event-loop-1 -> receive event for request B
T3: another worker -> response callback for A runs
T4: another worker -> ThreadLocal.get() does not have "trace-A"
~~~

An MDC-based logging library — usually implemented with `ThreadLocal` — can also print missing or lost correlation IDs if there is no mechanism to propagate/restore the data. Worse, if a thread is reused and old data was not cleaned up, logs can attach the **wrong request ID**.

## 4. Reactor Context: Context That Travels with the Subscription

Reactor provides two important types:

| Type | Role |
| --- | --- |
| `reactor.util.context.Context` | Key-value read/write interface; `put`, `delete`, and `putAll` operations create a new Context without mutating the old one directly. |
| `reactor.util.context.ContextView` | **Read-only** interface, used to retrieve values from the Context currently visible to an operator. |

Common APIs:

- `Context.of("traceId", "t-1")`: creates a Context with key/value pairs.
- `contextWrite(Context.of(...))` or `contextWrite(ctx -> ctx.put(key, value))`: provides a new Context to **upstream** operators.
- `Mono.deferContextual(view -> ...)` / `Flux.deferContextual(view -> ...)`: reads the current Context **at subscription time**, then creates the appropriate publisher.
- `view.get(key)`: retrieves the value; may throw `NoSuchElementException` if the key does not exist.
- `view.getOrDefault(key, fallback)` or `view.hasKey(key)`: handles keys that may be absent without relying on exceptions.

**Context is scoped to the subscription**, not a global Map shared across all requests. Two subscriptions to the same pipeline can receive different Contexts. This allows handling multiple concurrent requests without accidentally sharing each other's data.

Reactor Context is typically used for auxiliary metadata such as correlation IDs, trace spans, security context, or transaction context. Primary business data should still flow through `onNext` signals as `Mono<Order>`, `Flux<Item>`, DTOs, etc. When a method needs data to perform business calculations, do not put everything into Context just to avoid declaring parameters.

### Context Differs from Spring ApplicationContext

- Spring's `ApplicationContext` is the container that manages beans and application configuration; it typically outlives a single request.
- Reactor `Context` holds metadata for a subscription, accessed through the subscriber chain.
- HTTP request attributes/headers are HTTP metadata and do not automatically become Reactor Context unless the application or framework transfers them in.
- `ThreadLocal` is thread-bound data; on its own, it has no awareness of which subscription is active.

All of these contain the word "Context", but their **roles are not interchangeable**.

## 5. Direction of Context Propagation: Downstream -> Upstream

A common point of confusion: **data signals** normally flow from source through operators to subscriber, whereas **Context is propagated during subscription in the direction from downstream back to upstream**.

~~~text
Assembly (writing the pipeline):
source -> map -> flatMap -> contextWrite -> subscriber

At subscription time:
subscriber -- Context --> contextWrite -- new Context --> flatMap --> map --> source

When data is emitted:
source -- onNext/onError/onComplete --> map --> flatMap --> subscriber
~~~

`contextWrite` modifies the **Context seen by upstream operators** at the position where it is placed. It is not a command to "set a ThreadLocal for all code below" and does not automatically modify the Context of downstream operators.

For example:

~~~java
static final String KEY = "demo.traceId";

Mono<String> source = Mono.deferContextual(view -> {
    String trace = view.getOrDefault(KEY, "missing");
    return Mono.just(trace);
});

Mono<String> result = source
    .contextWrite(Context.of(KEY, "trace-17"));
~~~

When `result` is subscribed to, `source` sees `trace-17`. `Mono.deferContextual` reads the subscriber's Context when it runs; building the pipeline earlier **does not read** Context in the usual way.

### What If Multiple contextWrite Calls Set the Same Key?

~~~java
Mono<String> source = Mono.deferContextual(view ->
    Mono.just(view.<String>get("demo.key"))
);

Mono<String> result = source
    .contextWrite(ctx -> ctx.put("demo.key", "near-source"))
    .contextWrite(ctx -> ctx.put("demo.key", "near-subscriber"));
~~~

The source sees `"near-source"` because the write **closer to the source** executes as Context propagates upward and can overwrite a value with the same key set further downstream. This is useful for providing branch-specific configuration, though it can be confusing if you do not map out operator positions.

**Rule of thumb:** identify which operator needs to read the Context; place `contextWrite` **downstream of the section that needs to read it**, and use clearly namespaced keys to avoid accidental overwrites. Do not rely on the visual order of the `onNext` flow to infer Context scope.

## 6. Runnable Java 17 Example: ThreadLocal Is Lost, Context Remains

This standalone example intentionally uses `boundedElastic` to ensure the `Callable` runs on a different worker thread than the `main` thread. Neither Micrometer context-propagation nor a ThreadLocal-restoring hook is enabled, so you can directly observe the difference between the two mechanisms.

Create `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.6.8'
    testImplementation 'io.projectreactor:reactor-test:3.6.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.3'
}

application {
    mainClass = 'ReactorContextDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Create `src/main/java/ReactorContextDemo.java`:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.util.context.Context;

public class ReactorContextDemo {
    static final String CONTEXT_KEY = "demo.requestId";
    static final ThreadLocal<String> LEGACY_REQUEST_ID =
        new ThreadLocal<>();

    public static void main(String[] args) {
        LEGACY_REQUEST_ID.set("req-42");
        try {
            Mono<String> pipeline = Mono.deferContextual(view ->
                Mono.fromCallable(() -> {
                    String fromThreadLocal = LEGACY_REQUEST_ID.get();
                    String fromContext =
                        view.getOrDefault(CONTEXT_KEY, "missing");

                    return "worker ThreadLocal="
                        + (fromThreadLocal == null
                            ? "<missing>" : fromThreadLocal)
                        + "; Reactor Context=" + fromContext;
                }).subscribeOn(Schedulers.boundedElastic())
            ).contextWrite(Context.of(CONTEXT_KEY, "req-42"));

            System.out.println(
                "caller ThreadLocal=" + LEGACY_REQUEST_ID.get()
            );
            System.out.println(
                pipeline.block(Duration.ofSeconds(5))
            );

            Mono<String> shared = Mono.deferContextual(view -> {
                String value =
                    view.getOrDefault(CONTEXT_KEY, "missing");
                return Mono.just(value);
            });

            System.out.println("subscription A="
                + shared.contextWrite(
                    Context.of(CONTEXT_KEY, "A")).block());
            System.out.println("subscription B="
                + shared.contextWrite(
                    Context.of(CONTEXT_KEY, "B")).block());
        } finally {
            LEGACY_REQUEST_ID.remove();
        }
    }
}
~~~

Run from the project directory: `gradle run` (or `./gradlew run` if a Gradle Wrapper is present; on Windows use `gradlew.bat run`). The four stdout lines of **the program itself** are:

~~~text
caller ThreadLocal=req-42
worker ThreadLocal=<missing>; Reactor Context=req-42
subscription A=A
subscription B=B
~~~

**Why is this output reliable?**

1. `LEGACY_REQUEST_ID.set("req-42")` binds the value to the **thread running `main`**. The first log line reads on this same thread, so it sees the value.
2. `Mono.deferContextual` reads the subscription's `ContextView`. `contextWrite` at the end of the pipeline set `demo.requestId = req-42` for the upstream section.
3. `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` executes the callable on a `boundedElastic` worker. A regular `ThreadLocal` is not automatically propagated from the `main` thread to the worker, so `get()` returns `null`. The standalone example does not enable automatic ThreadLocal restoration.
4. `ContextView` was supplied by Reactor along the subscriber chain and can be read inside the callable via valid reference capture. Therefore, the value `req-42` is still present even though the callable runs on a different thread.
5. The next two subscriptions use **the same `Mono<String> shared`** but write different Contexts; the results are `A` and `B` respectively. This demonstrates per-subscription isolation.
6. `remove()` in `finally` cleans up the `main` thread's `ThreadLocal`; it does not change the Context values of the subscriptions already used.

`block(Duration)` is present only in the console program to wait and print results. **Do not copy calling `block()` into a WebFlux controller running on an event loop.** Return the publisher for the framework to subscribe to.

In a Spring Boot project, let the **Spring Boot BOM** manage compatible Reactor versions. The example pins a Reactor version solely so the small project runs standalone.

## 7. Reading Reactor Context After a Thread-Switching Boundary

The following example uses `publishOn` before a `flatMap`. Inside the inner publisher, `Mono.deferContextual` still reads the subscription's key:

~~~java
Mono<String> message = Mono.just("start")
    .publishOn(Schedulers.parallel())
    .flatMap(unused -> Mono.deferContextual(view -> {
        String traceId =
            view.getOrDefault("demo.traceId", "missing");
        return Mono.just("trace=" + traceId);
    }))
    .contextWrite(Context.of("demo.traceId", "trace-8"));
~~~

This is a **Reactor snippet that can be placed inside a method** with imports for `Mono`, `Schedulers`, and `Context`. When subscribed to and awaited successfully, the publisher emits `"trace=trace-8"`. There is no requirement that `flatMap` run on the same thread that created `Mono.just("start")`.

**Important point:** Context stays with the subscription **not** because `publishOn` copies all `ThreadLocal` variables, but because Reactor operators pass subscriber metadata through the Context mechanism. If a piece of code detaches processing onto a thread or callback system that does not use Reactor's subscriber chain, metadata must be passed via an appropriate API.

There is no need to attach `contextWrite` at every operator. With a clear scope, placing it once downstream of the processing section that needs it is sufficient. However, if you nest pipelines or compose multiple separate subscriptions, you must check which subscription the Context actually belongs to.

## 8. Context Is Immutable, While Values Inside It May Not Be

`Context` uses an immutable structure: operations create a new Context rather than modifying the old instance directly:

~~~java
Context first = Context.of("demo.traceId", "A");
Context second = first.put("demo.traceId", "B");

// first still holds "A"; second holds "B".
~~~

This works well when multiple parts of a pipeline use Context without needing a Map that could be mutated arbitrarily from different threads.

However, **the objects stored as values are not necessarily immutable**. If you place a mutable `HashMap`, a builder, or a shared stateful object into Context, multiple callbacks can still contend or observe inconsistent state.

Prefer:

- Small, immutable values: trace IDs, correlation IDs, authenticated tenant identifiers, scoped configuration.
- Namespaced keys or dedicated key types to avoid name collisions with other libraries.
- Security/sensitive data strictly within designed boundaries; do not blindly copy all headers, tokens, or large payloads into Context.
- Pure business computations using parameters or `onNext` signals instead of turning Context into an arbitrary state store.

Example of a dedicated typed key instead of a generic string:

~~~java
static final Object REQUEST_ID_KEY = new Object();

Mono<String> action = Mono.deferContextual(view ->
    Mono.just(view.get(REQUEST_ID_KEY))
).contextWrite(Context.of(REQUEST_ID_KEY, "req-42"));
~~~

This is an integration snippet requiring imports for `Mono` and `Context`. When both writer and reader use **the same key object**, the risk of colliding with keys from other libraries decreases. In practice, make the key an accessible `static final` constant used consistently; do not create separate `new Object()` instances in two classes and expect them to match.

## 9. Reactor Context Is Not "MDC That Just Works Automatically"

SLF4J/Logback MDC is normally backed by `ThreadLocal`. Therefore, statements like:

~~~java
MDC.put("traceId", "trace-A");
// An operator runs asynchronously...
log.info("Processing");
~~~

are not sufficient to guarantee that the log line will be printed with the right `traceId` once signals have switched threads. In a multi-request system, there is also a risk that a reused worker retains an old MDC value if code forgets cleanup.

Appropriate ways to handle this:

1. **Prefer official observability integrations** from Spring Boot/Micrometer Tracing and Reactor-compatible instrumentation. Verify versions, context propagation configuration, and registered keys/accessors rather than assuming MDC is always restored.
2. When doing it manually, read the correlation ID from Reactor `ContextView` at the processing point and **set/restore/clear MDC within that specific callback's scope**, for example using a scope mechanism or `try/finally`. Do not set it once and leave MDC lingering on a worker indefinitely.
3. If you only need the correlation ID in a business record or response, passing it as a parameter/DTO is usually easier to test than relying on implicit MDC.

Simple design example when MDC is not needed:

~~~java
Mono<String> result = Mono.deferContextual(view -> {
    String traceId =
        view.getOrDefault("demo.traceId", "unknown");

    return service.fetch()
        .map(value -> "trace=" + traceId + "; value=" + value);
});
~~~

This is an **integration snippet**; `service.fetch()` returns `Mono<String>`. Here, the trace ID is retrieved from Context and used explicitly in the logic, independent of threads or logging frameworks.

**Do not store a `ContextView` in a global variable shared across requests.** Read the Context for the current subscription and use the needed data within that scope.

## 10. Micrometer Context Propagation: A Bridge for Legacy ThreadLocal

Starting with Reactor Core 3.5+, Reactor supports integration with the SPI of `io.micrometer:context-propagation`. Its purpose is to connect different Context forms with libraries that still rely on `ThreadLocal` (such as tracing/MDC). This mechanism **adds bridging capability**; it does not change the underlying nature of `ThreadLocal`.

Key concepts:

| Component | Role |
| --- | --- |
| `ThreadLocalAccessor` | Defines how to read/write/reset a specific `ThreadLocal`, bound to a key. |
| `ContextRegistry` | Registers accessors so the library knows how to transfer state. |
| `contextCapture()` | Captures registered `ThreadLocal` values at subscription time and places them into Reactor Context for the upstream portion. |
| `Hooks.enableAutomaticContextPropagation()` | Enables automatic restoration of `ThreadLocal` from Reactor Context at supported boundaries, applying to new subscriptions. |
| Default mode (limited) | Certain operators such as `handle` and `tap` can create a ThreadLocal restoration scope when the appropriate integration is present. |

**Prerequisites must be clear:** having the right `context-propagation` library on the classpath, registering the required `ThreadLocalAccessor` instances, enabling the hook at the right time, and having the right subscription scope. Calling `Hooks.enableAutomaticContextPropagation()` without matching accessors **does not automatically move arbitrary `ThreadLocal` variables**.

Illustrative configuration example at application startup:

~~~java
import reactor.core.publisher.Hooks;

// Use only when the application has configured Context Propagation
// and the required ThreadLocalAccessors.
Hooks.enableAutomaticContextPropagation();
~~~

The snippet above is **not a standalone program** and does not recommend enabling the hook just to handle a single custom `ThreadLocal`. This is a **global** setting, so it should be configured according to your observability architecture and measured for performance impact.

### Default Mode and Automatic Mode

In default mode, do not assume every `map` callback on a new thread will see the same MDC/ThreadLocal. In automatic mode, Reactor attempts to restore registered state from Context at appropriate execution points, including across thread switches; it also needs to clean up state within the proper scope to avoid leaking data across subscriptions.

Reactor documentation recommends enabling the hook early at application startup because this change applies to **subscriptions created afterward**. Capturing the current thread's `ThreadLocal` into Context is also a separate step; depending on mode and subscription API (such as certain blocking terminal APIs), automatic capture may occur. Do not infer that the hook automatically captures any variable at any moment.

**Still prioritize proper Reactor Context design:** treat Reactor Context as the subscription's source of context; use the bridge when compatibility with ThreadLocal-based Java/observability libraries is required. Bridging has overhead and limitations; measure under realistic load.

## 11. Boundaries Where Context Can Be Lost or Unavailable

### 11.1. Creating a Separate Subscription Manually

~~~java
public Mono<String> wrong() {
    innerService.doWork().subscribe();
    return Mono.just("accepted");
}
~~~

This is an integration snippet. Calling `subscribe()` internally creates a **new subscription** with its own lifecycle; the task may continue after the caller receives the response, and errors, cancellation, and the caller's context will not propagate as you expect.

Replace with:

~~~java
public Mono<String> correct() {
    return innerService.doWork()
        .thenReturn("accepted");
}
~~~

Now the caller or WebFlux framework subscribes to a single pipeline, so completion, errors, cancellation, and Reactor Context are composed according to the proper model. If `innerService.doWork()` is already a standard reactive publisher, there is no need to call `subscribe()` manually at every service layer.

### 11.2. Escaping to a Plain Java Executor or CompletableFuture

A task submitted directly to `ExecutorService.submit` or `CompletableFuture.supplyAsync` may run on a thread that does not participate in the subscriber chain. Inside that plain callback, you cannot call `Mono.deferContextual` to "read the current Context" if there is no corresponding subscription.

The solution is to **pass the needed data as parameters**, or use a properly configured bridge/context-propagation setup:

~~~java
Mono<String> result = Mono.deferContextual(view -> {
    String traceId =
        view.getOrDefault("demo.traceId", "missing");

    return Mono.fromFuture(
        java.util.concurrent.CompletableFuture.supplyAsync(
            () -> "processed-" + traceId
        )
    );
});
~~~

This integration snippet illustrates **capturing a String from Reactor Context before dispatching work to a `CompletableFuture`**. The callback uses the explicitly captured `traceId` variable instead of relying on `ThreadLocal`. In a real application, use a properly managed and bounded executor. `CompletableFuture.supplyAsync` on the common pool is not a good default choice for potentially long-running blocking I/O calls.

### 11.3. Sending Across a Network or Message Broker

Reactor Context exists only inside the pipeline of its corresponding process/subscription. It **does not automatically become an HTTP header, a Kafka header, or a network message**. If you want a trace ID to cross service boundaries, you must use compatible instrumentation (tracing propagation) or explicitly map the data to headers/metadata per your contract.

Similarly, when processing messages received from a broker, you must **re-establish context** for the message-handling subscription from validated metadata sources. Do not expect the sender process's Context to still exist in the receiver process.

## 12. Injecting Context into a WebFlux Pipeline in a WebFilter

In WebFlux, a `WebFilter` can attach a new correlation ID to Reactor Context for downstream request processing. The following snippet uses a server-generated UUID:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class CorrelationFilter implements WebFilter {
    public static final String TRACE_KEY = "app.traceId";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String traceId = UUID.randomUUID().toString();

        return chain.filter(exchange)
            .contextWrite(ctx -> ctx.put(TRACE_KEY, traceId));
    }
}
~~~

This is an **integration snippet for a Spring Boot WebFlux application**, not a standalone runnable program. It requires the `spring-boot-starter-webflux` dependency and appropriate bean scanning.

**Explanation:**

1. `WebFilter` generates a dedicated trace ID for the request execution.
2. `chain.filter(exchange)` returns a `Mono<Void>` representing subsequent processing.
3. `contextWrite` establishes the context for upstream subscribers/operators in the chain when the framework subscribes to the publisher.
4. Inner controllers/services can read the trace ID via `Mono.deferContextual` without having to assume they run on the same thread as the filter.
5. `Mono<Void>` indicates completion or error of the chain rather than emitting a trace ID value; Context acts as metadata attached to the subscription.

This snippet only shows the **Context propagation mechanism**. If you want to return the trace ID via an HTTP header, adding data to the response requires a separate operation on `ServerHttpResponse`. If you want to send the trace ID to another service, you must map it to a header in `WebClient` or use tracing instrumentation.

### Reading Context in a Service or Controller

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class CorrelationService {
    public Mono<String> currentTrace() {
        return Mono.deferContextual(view -> {
            String traceId = view.getOrDefault(
                CorrelationFilter.TRACE_KEY, "missing");
            return Mono.just(traceId);
        });
    }
}
~~~

`currentTrace()` **does not call `ThreadLocal.get()`**. It creates a publisher that reads the subscription's Context at runtime. If called inside a chain wrapped by `CorrelationFilter`, the value from the filter can reach the service. If the service is subscribed to independently outside the WebFlux filter, the fallback result is `"missing"` according to the code's contract.

A controller can look like this:

~~~java
@GetMapping("/debug/correlation")
public Mono<String> correlation() {
    return correlationService.currentTrace();
}
~~~

This is a controller snippet that requires declaring `correlationService` and the corresponding WebFlux annotations/imports. **Do not call `subscribe()` manually in a controller**; the WebFlux framework will subscribe to the returned value.

## 13. Reactor Context and Reactive Spring Security / Transactions

Reactive frameworks also rely on subscriber-bound context rather than relying solely on threads.

### Reactive Spring Security

In WebFlux with reactive Spring Security, the authentication context can be accessed via:

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<String> username =
    ReactiveSecurityContextHolder.getContext()
        .map(securityContext ->
            securityContext.getAuthentication().getName()
        );
~~~

This is an **integration snippet** that requires reactive Spring Security to be configured and a valid `Authentication`. Do not equate it with the imperative `SecurityContextHolder.getContext()`: when a pipeline switches threads, a traditional thread-bound `ThreadLocal` may be absent if no suitable bridge is present.

You should not manually modify Spring Security's internal Context keys without an explicit API/contract. Prefer `ReactiveSecurityContextHolder` and official security filters.

### Spring Reactive Transactions

Spring's reactive transaction manager uses context associated with reactive execution instead of binding the transaction to a request thread by default as in imperative code. When using `TransactionalOperator` or properly configured `@Transactional` on reactive methods, the transaction can follow the reactive pipeline.

Avoid calling `subscribe()` manually inside a service that uses reactive transactions: creating an independent subscription can detach from the expected transaction scope. Do not manually copy or edit transaction context keys with `contextWrite` without an official API.

**General principle:** context only follows **the subscriber chain managed by the framework**. Any step executed outside that chain needs an explicit mechanism to bridge scope.

## 14. Observing and Testing Context in Reactor

Instead of only checking thread names, test **which context data is visible on which subscription**. For example, when the same pipeline is used by two requests, their Contexts must not mix, and switching schedulers must not lose the key.

Create `src/test/java/ReactorContextTest.java` in the project from section 6:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

class ReactorContextTest {
    private static final String KEY = "demo.requestId";

    @Test
    void contextSurvivesPublishOn() {
        Mono<String> pipeline = Mono.just("work")
            .publishOn(Schedulers.parallel())
            .flatMap(value ->
                Mono.deferContextual(view -> {
                    String id = view.getOrDefault(KEY, "missing");
                    return Mono.just(id);
                })
            )
            .contextWrite(Context.of(KEY, "req-7"));

        StepVerifier.create(pipeline)
            .expectNext("req-7")
            .verifyComplete();
    }

    @Test
    void twoSubscriptionsHaveIndependentValues() {
        Mono<String> shared = Mono.deferContextual(view -> {
            String id = view.getOrDefault(KEY, "missing");
            return Mono.just(id);
        });

        StepVerifier.create(
                shared.contextWrite(Context.of(KEY, "A")))
            .expectNext("A")
            .verifyComplete();

        StepVerifier.create(
                shared.contextWrite(Context.of(KEY, "B")))
            .expectNext("B")
            .verifyComplete();
    }

    @Test
    void contextWriteClosestToSourceOverridesSameKey() {
        Mono<String> pipeline = Mono.deferContextual(view -> {
            String id = view.getOrDefault(KEY, "missing");
            return Mono.just(id);
        })
        .contextWrite(ctx -> ctx.put(KEY, "near-source"))
        .contextWrite(ctx -> ctx.put(KEY, "near-subscriber"));

        StepVerifier.create(pipeline)
            .expectNext("near-source")
            .verifyComplete();
    }

    @Test
    void missingKeyCanBeHandledExplicitly() {
        Mono<String> pipeline = Mono.deferContextual(view ->
            Mono.just(view.getOrDefault(KEY, "missing"))
        );

        StepVerifier.create(pipeline)
            .expectNext("missing")
            .verifyComplete();
    }
}
~~~

Run `gradle test` or the corresponding Gradle Wrapper command. **All four tests are expected to PASS**:

- `contextSurvivesPublishOn`: Context remains readable after signals switch schedulers.
- `twoSubscriptionsHaveIndependentValues`: the same `shared` source receives A and B independently across two subscriptions.
- `contextWriteClosestToSourceOverridesSameKey`: the write position determines the value seen by upstream operators.
- `missingKeyCanBeHandledExplicitly`: a missing key is handled explicitly via a default rather than throwing an exception.

**Limitations:** these tests verify Reactor Core behavior; they do not yet verify tracing/MDC integration, security, transactions, or context propagation across external executors. Those integrations require dedicated tests with actual dependencies, accessor/hook configuration, and real runtime boundaries.

## 15. Common Mistakes and Fixes

| Mistake | Why It Breaks | How to Fix |
| --- | --- | --- |
| Calling `ThreadLocal.set(...)` in a WebFilter and `get()` in every step | The pipeline may switch threads; workers are shared across multiple requests | Use Reactor `contextWrite` and `deferContextual` or official integrations |
| Using `InheritableThreadLocal` to propagate across a thread pool | Semantics apply only when creating child threads, not per task/subscription | Propagate context per subscription or capture/restore with proper scope |
| Assuming `Mono`/`Flux` automatically run on a new thread | Reactive APIs do not guarantee a scheduler on their own | Understand the source and `publishOn`/`subscribeOn` operators |
| Placing `contextWrite` upstream of the point that needs to read it | Context flows from downstream to upstream at subscription time | Place `contextWrite` downstream of the section that needs to read it |
| Calling `contextWrite` thinking it mutates a global Map | Context is immutable and scoped per subscription | Treat `put` as creating a new Context for upstream |
| Using `view.get(KEY)` for a key that is not guaranteed to exist | Can throw `NoSuchElementException` | Use `hasKey`/`getOrDefault` or enforce a required invariant |
| Creating different `new Object()` keys at write and read sites | The two keys do not match | Use the same shared constant/key object |
| Putting a mutable object in Context and modifying it from multiple workers | Inner data can race even though Context itself is immutable | Prefer immutable values and clear scoping |
| Calling `subscribe()` manually in a service or controller | Creates a new subscription/lifecycle, breaking error and context propagation | Return the composed publisher for the caller/framework to subscribe |
| Assuming Context automatically becomes an HTTP header or Kafka header | Metadata exists only within the reactive subscription scope | Map explicitly to protocol metadata or use tracing instrumentation |
| Assuming `Hooks.enableAutomaticContextPropagation()` protects every `ThreadLocal` | Depends on libraries, accessors, mode, subscription timing, and registered scope | Configure and test bridging deliberately |
| Forgetting to clean up MDC/ThreadLocal on reused workers | Leaks metadata across other requests | Use managed scopes and clean up via `finally`/integration |
| Calling `block()` in a WebFlux handler to obtain Context/data | Can block or be rejected on non-blocking threads | Keep processing inside `Mono`/`Flux` and return the publisher |
| Checking only thread names in logs without checking trace IDs | Thread names do not confirm the correct request value | Test Context per subscription and observe trace/correlation end-to-end |

## 16. Checklist for Applying This to a WebFlux Application

Before concluding that a system propagates context properly, verify:

1. **Who creates the metadata?** From a validated HTTP header, tracing instrumentation, security filter, or server-generated code? Define keys and values clearly.
2. **Which subscription uses it?** Context must be attached to the chain that WebFlux subscribes to, not to an accidental side subscription created with `subscribe()`.
3. **Are there scheduler switches?** Test `publishOn`, `subscribeOn`, async I/O, and nested publishers with the same correlation ID.
4. **Are there boundaries outside Reactor?** For callback libraries, `CompletableFuture`, executors, brokers, and HTTP, pass metadata explicitly or configure compatible bridging.
5. **Are MDC/legacy ThreadLocals used?** Verify Micrometer context-propagation, accessors, restore/cleanup, and runtime overhead; do not rely on "it works automatically" without testing.
6. **Are values sensitive or mutable?** Limit data stored in Context, namespace keys, guard against shared mutable state, and prevent uncontrolled logging.
7. **Can two concurrent requests be tested?** Use distinct trace IDs and verify there is no cross-request leakage when workers are reused.
8. **Does the framework manage it separately?** Reactive Spring Security and reactive transactions provide Context-aware APIs; prefer official APIs.

**Remember:** `ThreadLocal` answers the question **"which thread is currently running?"**, whereas Reactor `Context` helps answer **"which subscription is processing this signal?"**. For reactive chains that can switch workers, request context must be managed per subscription with clear boundaries. `ThreadLocal` can still be used inside controlled restore/cleanup scopes, but `ThreadLocal.set/get` alone is not enough to guarantee data survives across thread-switching chains.

## References

- Project Reactor — Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Project Reactor — Context-Propagation Support: https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html
- Project Reactor — Threading and Schedulers: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Project Reactor — `Mono` API (`deferContextual`, `contextWrite`): https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Spring Framework — WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Security — Reactive Security Context: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Framework — Programmatic reactive transaction management: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
