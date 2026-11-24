# Integrating Context Propagation and Limits with MDC and External Libraries

**Context:** Spring Framework – Reactive, **Reactor Context** chapter. This lesson explains how to propagate request IDs, trace IDs, tenants, and metadata across Reactor operators; how to integrate with **SLF4J MDC** and `ThreadLocal`-based imperative libraries; and the limits of automatic context propagation.

## 1. The Problem: One Request Can Run Across Many Threads

In traditional imperative applications, a request is usually processed mostly on a single thread. Logging frameworks such as SLF4J MDC store diagnostic information in a `ThreadLocal`, for example `requestId` or `traceId`. When writing logs, the formatter reads the current thread's MDC to append the corresponding fields.

In Reactor/WebFlux, a request is not permanently tied to one thread. Steps can run on a Netty event-loop, another thread after `publishOn`/`subscribeOn`, a Reactor scheduler, virtual threads, an executor created by an external library, or an asynchronous callback after the original thread has moved on to another request.

Therefore, **the current thread's MDC is not a reliable store for the entire lifecycle of a reactive request**. A value may be missing on the new thread; worse, a leftover value from a previous request may be read by mistake when the thread is reused.

Common buggy example:

```java
MDC.put("requestId", requestId);

return service.load()
        .publishOn(Schedulers.parallel())
        .doOnNext(value -> log.info("loaded {}", value));
```

This is an **erroneous illustration**: MDC is set on the thread assembling the controller, whereas the callback after `publishOn` may run on another thread. Without a context restoration mechanism, the log lacks the expected request ID. Nor should you simply call `MDC.clear()` at the end of the controller, because the controller can return the publisher immediately while signals arrive later.

The solution is to distinguish two kinds of context:

1. **Reactor Context:** the subscription-scoped data source propagated through the reactive pipeline.
2. **ThreadLocal/MDC:** temporary thread-bound state that should only be restored within the execution scope where it is needed.

Reactor Context is the right place to hold a reactive flow's metadata. MDC and other `ThreadLocal`s are **compatibility targets** when calling legacy code or logging with libraries that inherently rely on the current thread.

## 2. How Does Reactor Context Differ from MDC?

| Feature | Reactor Context | SLF4J MDC |
| --- | --- | --- |
| Ownership scope | Bound to subscriber/subscription | Bound to the current thread |
| Propagation | Per subscription; context flows from downstream to upstream at subscribe time | Does not transfer automatically when the pipeline switches threads |
| Data structure | Map-like, immutable; writes produce a new Context | Map of strings stored in the logging backend's `ThreadLocal` |
| Concurrent requests | Each subscription has its own context | Safe only when set/restored properly per thread; leaks easily if mismanaged |
| Read mechanism | Via `deferContextual`, `transformDeferredContextual`, `Signal.getContextView` | Via `MDC.get` inside a restored scope |
| Role | Holds request/trace/tenant metadata in a reactive flow | Compatibility with log formatters and existing imperative code |

A Reactor Context is not a full copy of MDC. It only holds key/value pairs explicitly placed into context, such as:

```java
.contextWrite(context -> context.put("requestId", "req-42"))
```

Operators **above** the `contextWrite` position can read that key. Context propagates from downstream to upstream during subscription, so where you place `contextWrite` matters. Operators below it do not automatically see the new context in the way operators above it do.

You can read the value without `ThreadLocal`:

```java
Mono<String> requestId = Mono.deferContextual(context ->
        Mono.just(context.get("requestId")));
```

This is the preferred approach when you control the code: pass context explicitly rather than calling `MDC.get` inside every business method.

### 2.1. Context Is Per-Subscription Data, Not a Global Variable

Reactor Context is designed so each subscriber can carry its own value. Two requests running on the same event loop do not share a request ID because of that. Do not put request metadata into a mutable `static` variable, singleton holder, or global `ThreadLocal` and expect Reactor to separate requests automatically.

Objects stored inside Context can still be mutable. Context's immutability does not automatically make objects inside it thread-safe. Prefer immutable value objects, strings, or metadata with clear contracts; never store a shared mutable map and update it from parallel branches.

## 3. Which Metadata Should Be Propagated?

A pipeline can carry:

- **Correlation/request ID:** connects logs belonging to the same request or cross-layer operation.
- **Trace/span context:** links parent/child spans, trace ID, and instrumentation-standard tracing details.
- **Tenant ID:** routes to a tenant or selects appropriate configuration, provided it was authenticated at a trusted boundary.
- **Locale or timezone:** for formatting data and messages.
- **Security context/principal:** identity and authorities via supported security mechanisms.
- **Observability info:** current observation, baggage, or metadata for metrics/traces.

Do not use context to carry large business payloads, binary data, full request bodies, secret tokens, passwords, or complex mutable objects. Context is neither a cache nor a substitute for function parameters. Data required to compute results should be passed via explicit input/output types.

**Cardinality and security limits:** request IDs and trace IDs usually have high cardinality, making them suitable for logs or traces but unsuitable as unbounded-cardinality metric tags. Never log access tokens, session secrets, or sensitive personal data into MDC/logs.

## 4. Integrating Reactor Context with MDC Using `doOnEach`

A transparent and controlled approach is to read data from Reactor Context **at the exact logging point**, temporarily place it into MDC, perform the log statement, and restore state right after the callback.

SLF4J 2 provides `MDC.putCloseable(key, value)`. The returned object works with try-with-resources; when closed, the temporary value is removed from MDC. This prevents request A's request ID from lingering on a worker and being picked up by request B.

### 4.1. Logging Helper for `onNext` Signals

```java
import java.util.Optional;
import java.util.function.Consumer;

import org.slf4j.MDC;
import reactor.core.publisher.Signal;

public final class ReactorMdc {
    private ReactorMdc() {}

    public static <T> Consumer<Signal<T>> logOnNext(
            Consumer<T> logStatement) {

        return signal -> {
            if (!signal.isOnNext()) {
                return;
            }

            Optional<String> requestId =
                    signal.getContextView().getOrEmpty("requestId");

            if (requestId.isPresent()) {
                try (MDC.MDCCloseable ignored =
                             MDC.putCloseable("requestId", requestId.get())) {
                    logStatement.accept(signal.get());
                }
            } else {
                logStatement.accept(signal.get());
            }
        };
    }
}
```

Usage in a pipeline:

```java
return service.load()
        .doOnEach(ReactorMdc.logOnNext(value ->
                log.info("loaded {}", value)))
        .contextWrite(context ->
                context.put("requestId", requestId));
```

This is an **illustrative helper and usage**, requiring application-defined `service`, `log`, and `requestId`. Key points:

1. `doOnEach` receives a `Signal`, not just the value. `Signal` carries the `ContextView` matching the subscription.
2. Only `onNext` is handled in this helper; if you need error logging, write a separate helper checking `isOnError` and reading `getThrowable`.
3. If the key has a value, the helper puts it into MDC strictly for the logging callback. Try-with-resources then closes the scope.
4. If the key does not exist, the helper still logs normally without inventing a fake request ID.
5. `contextWrite` is placed at the end of the chain so the `doOnEach` operator above it can read the key.

Do not write `MDC.put` and leave it set in a callback. With shared thread pools, every callback must restore or clear temporary state upon completion.

### 4.2. Standalone Java 17+ Program with Deterministic Output

The following example uses a scheduler to prove the callback can run on another thread, while avoiding printing thread names so the output does not depend on which worker is chosen.

File `src/main/java/demo/ReactorMdcDemo.java`:

```java
package demo;

import java.time.Duration;
import java.util.Optional;
import java.util.function.Consumer;

import org.slf4j.MDC;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Signal;
import reactor.core.scheduler.Schedulers;
import reactor.util.context.Context;

public final class ReactorMdcDemo {

    private static <T> Consumer<Signal<T>> logOnNext(
            Consumer<T> logStatement) {

        return signal -> {
            if (!signal.isOnNext()) {
                return;
            }

            Optional<String> requestId =
                    signal.getContextView().getOrEmpty("requestId");

            if (requestId.isPresent()) {
                try (MDC.MDCCloseable ignored =
                             MDC.putCloseable("requestId", requestId.get())) {
                    logStatement.accept(signal.get());
                }
            } else {
                logStatement.accept(signal.get());
            }
        };
    }

    public static void main(String[] args) {
        Flux.just("created", "updated")
                .publishOn(Schedulers.parallel())
                .doOnEach(logOnNext(value ->
                        System.out.println(
                                "requestId=" + MDC.get("requestId")
                                        + ", event=" + value)))
                .contextWrite(Context.of("requestId", "req-42"))
                .blockLast(Duration.ofSeconds(5));
    }
}
```

**Dependencies:** Java 17+, `reactor-core`, `slf4j-api` 2.x, and a logging backend supporting MDC, such as SLF4J 2–compatible Logback. In a Spring Boot project that already includes `spring-boot-starter-webflux` and the appropriate logging starter, you normally do not pick these dependency versions manually; let the BOM manage them. When running standalone, include compatible JARs on the classpath.

Manual run commands (with required JARs placed in the `lib` directory):

```bash
# Linux/macOS
mkdir -p out
javac -cp "lib/*" -d out src/main/java/demo/ReactorMdcDemo.java
java -cp "out:lib/*" demo.ReactorMdcDemo
```

```powershell
# Windows PowerShell
New-Item -ItemType Directory -Force out
javac -cp "lib/*" -d out src/main/java/demo/ReactorMdcDemo.java
java -cp "out;lib/*" demo.ReactorMdcDemo
```

**Exact stdout:**

```text
requestId=req-42, event=created
requestId=req-42, event=updated
```

The synchronous source emits two elements in order; `publishOn` shifts downstream processing onto a scheduler. `doOnEach` reads the request ID from Reactor Context and puts it into MDC only while logging. `MDC.get` returns the expected value inside the callback. When the callback finishes, the scope closes, leaving no request ID on the worker.

**Scope of the example:** the helper above only covers logging inside `doOnEach` callbacks. It does not automatically make arbitrary external library calls see MDC, nor does it propagate the request ID over HTTP to another service.

### 4.3. Error Logging Also Needs MDC Restoration

If you want to log errors with the same request ID, use a dedicated helper:

```java
public static Consumer<Signal<?>> logOnError(
        Consumer<Throwable> logStatement) {

    return signal -> {
        if (!signal.isOnError()) {
            return;
        }

        Optional<String> requestId =
                signal.getContextView().getOrEmpty("requestId");

        if (requestId.isPresent()) {
            try (MDC.MDCCloseable ignored =
                         MDC.putCloseable("requestId", requestId.get())) {
                logStatement.accept(signal.getThrowable());
            }
        } else {
            logStatement.accept(signal.getThrowable());
        }
    };
}
```

Wiring into the pipeline:

```java
return service.load()
        .doOnEach(ReactorMdc.logOnNext(
                value -> log.info("loaded {}", value)))
        .doOnEach(ReactorMdc.logOnError(
                error -> log.error("load failed", error)))
        .contextWrite(context ->
                context.put("requestId", requestId));
```

This is **illustrative code**, not a standalone class. When logging terminal signals, remember `doOnEach` receives multiple signal types; helpers must check the right signal type before reading a value or throwable.

## 5. Writing and Reading Context Properly

### 5.1. Use `contextWrite` When Metadata Is Known

If the request ID has been determined at the controller or request-ingestion layer, write it directly:

```java
return service.findOrders()
        .map(this::toDto)
        .contextWrite(context -> context
                .put("requestId", requestId)
                .put("tenantId", tenantId));
```

This is illustrative code with application-defined `service`, `toDto`, `requestId`, and `tenantId`. Because Reactor Context is immutable, each `put` creates a new Context. You can chain multiple `contextWrite` calls; understand merge/override order clearly to avoid accidentally overwriting values for the same key.

Use namespaced keys or constants instead of scattered string literals:

```java
static final String REQUEST_ID = "app.requestId";
static final String TENANT_ID = "app.tenantId";
```

This prevents two libraries from picking the same key name with different meanings.

### 5.2. Use `deferContextual` to Read Context

`deferContextual` creates a publisher based on the Context present at subscription:

```java
Mono<OrderResult> result = Mono.deferContextual(context -> {
    String requestId = context.get("app.requestId");
    String tenantId = context.get("app.tenantId");

    return orderService.find(tenantId)
            .map(order -> new OrderResult(requestId, order));
});
```

This is **illustrative code** with application-defined domain types. If a key might be absent, use `hasKey` or `getOrDefault` instead of calling `get` directly and receiving an exception when missing.

There is no need to copy Reactor Context into MDC just to read a value in business logic. When you own the code, read directly from `ContextView` or pass the value as a method argument.

### 5.3. `contextWrite` and `contextCapture` Differ

| Operator | Purpose | Value source |
| --- | --- | --- |
| `contextWrite` | Writes/merges values into Reactor Context | Values you supply directly |
| `contextCapture` | Captures registered `ThreadLocal`s at subscribe time into Reactor Context | Context Propagation registry and current `ThreadLocal`s |
| `deferContextual` | Reads Reactor Context at subscription | Subscriber's Reactor Context |
| `transformDeferredContextual` | Transforms a publisher based on Context | `ContextView` and current publisher |

Example where imperative code sets MDC before launching Reactor:

```java
MDC.put("requestId", "req-42");

try {
    return service.load()
            .contextCapture();
} finally {
    MDC.remove("requestId");
}
```

This is only **illustrative code** and only works when `requestId` is registered with a `ThreadLocalAccessor` in Context Propagation. `contextCapture` captures `ThreadLocal`s at **subscription time**, not at assembly time. Therefore, if the publisher is subscribed to after `finally` has cleared MDC, there may no longer be a request ID in `ThreadLocal` to capture.

In a WebFlux controller, the request is already inside the reactive lifecycle and the framework may populate observation/security metadata into Reactor Context. For custom data, it is usually clearer to write directly with `contextWrite`. Do not add `contextCapture` out of habit if you have not verified what is in `ThreadLocal` and when subscription occurs.

## 6. Micrometer Context Propagation: Bridge Between Context and `ThreadLocal`

Project Reactor integrates with the `io.micrometer:context-propagation` SPI starting in Reactor Core 3.5.0. That library provides these abstractions:

- **`ThreadLocalAccessor`:** reads, sets, and clears the value of a specific `ThreadLocal`.
- **`ContextAccessor`:** enables reading/writing a map-like context representation.
- **`ContextRegistry`:** registers accessors used to bridge different context representations.
- **`ContextSnapshot`:** captures context values and restores `ThreadLocal`s within a scope.
- **`ContextSnapshotFactory`:** creates snapshots from current `ThreadLocal`s or from a supplied context.

Reactor understands `Context`/`ContextView` through `ReactorContextAccessor`, loaded via `ServiceLoader`. When both `reactor-core` and `context-propagation` are on the classpath, you do not need to write an accessor for Reactor Context yourself.

Micrometer Context Propagation does not replace Reactor Context or `ThreadLocal`. It **helps cross boundaries** between them: imperative code can keep using `ThreadLocal`; Reactor code should use Reactor Context; when calling an imperative component, the library can restore `ThreadLocal`s within the right scope.

### 6.1. Two Modes: `limited` and `automatic`

| Mode | Behavior | When to consider |
| --- | --- | --- |
| **Default / limited** | Only selected operators such as `handle` and `tap` restore `ThreadLocal` inside callbacks when Context Propagation and a suitable context snapshot are present | When you want to limit overhead and control bridge points |
| **Automatic** | Reactor operators restore `ThreadLocal`s across thread boundaries based on Reactor Context and registered accessors | When the application needs broad compatibility with imperative libraries and accepts the corresponding cost |

Important version milestones:

- **Reactor Core 3.5.0:** integrated the Context Propagation SPI; introduced limited mode, `contextCapture`, and changes supporting `ThreadLocal` restoration in select operators.
- **Reactor Core 3.5.3:** added `Hooks.enableAutomaticContextPropagation` to enable automatic mode.
- Micrometer documentation for Reactor 3.5.3+ examples notes a baseline set of versions: Reactor 3.5.3, Context Propagation 1.0.3, Micrometer 1.10.8, and Micrometer Tracing 1.0.7. This is a **documentation example reference**, not a mandatory version set for every modern application.
- **Spring Boot 3.2+:** provides `spring.reactor.context-propagation` with `limited` and `auto` modes. The default is `limited` in Boot 3.2.x docs; check your application's actual BOM/version.

Do not mix versions manually if using the Spring Boot BOM. Verify runtime dependencies so Reactor, Micrometer, Micrometer Tracing, and Context Propagation remain compatible.

### 6.2. Enabling Automatic Mode Directly in Reactor

If not using Spring Boot configuration, you can enable the hook at application startup:

```java
import reactor.core.publisher.Hooks;

public final class Application {
    public static void main(String[] args) {
        Hooks.enableAutomaticContextPropagation();

        // Initialize and run the application after enabling the hook.
    }
}
```

This is a **startup template** with application startup omitted. The hook is global configuration for the shared Reactor runtime and **applies only to new subscriptions**. Therefore, enable it before creating subscriptions that need context propagation; the safe approach is enabling it during startup, not late after requests are already running.

The hook does not generate request IDs or trace IDs on its own. It only restores `ThreadLocal`s that have matching accessors from values present in Reactor Context. If Context lacks a key, there is no value to restore.

### 6.3. Enabling Automatic Mode in Spring Boot

In `src/main/resources/application.properties`:

```properties
spring.reactor.context-propagation=auto
```

Or YAML:

```yaml
spring:
  reactor:
    context-propagation: auto
```

Spring Boot configures Reactor according to this property at application startup. When using Boot, prefer one clear configuration place and avoid calling the hook redundantly across libraries or static initializers.

In default `limited` mode, `handle` and `tap` support restoring `ThreadLocal` inside callbacks when Context Propagation is present and Context was properly captured/written. Never assume `doOnNext`, `map`, or arbitrary callbacks will see MDC in `limited` mode. If logging in `doOnEach` is all you need, the manual helper in section 4 is a transparent choice.

For `@Async` and Spring Boot auto-configured executors, that is a separate context-propagation path from Reactor. Boot has its own property `spring.task.execution.propagate-context`; custom executors need `ContextPropagatingTaskDecorator`. Enabling Reactor `auto` mode does not automatically configure every external `ExecutorService`.

## 7. Registering Accessors for MDC or External Libraries

### 7.1. Using `Slf4jThreadLocalAccessor` for Specific MDC Keys

Micrometer Context Propagation includes `Slf4jThreadLocalAccessor` to carry MDC contents across thread boundaries. The accessor can copy all of MDC or only specific keys. Example registering one key:

```java
import io.micrometer.context.ContextRegistry;
import io.micrometer.context.integration.Slf4jThreadLocalAccessor;

ContextRegistry.getInstance()
        .registerThreadLocalAccessor(
                new Slf4jThreadLocalAccessor("requestId"));
```

This accessor is available since Context Propagation 1.1.1. When using selective keys, Reactor Context stores the value under the accessor's internal key (the `Slf4jThreadLocalAccessor.KEY` constant); the accessor manages the MDC map for registered keys. If you write Context directly yourself, follow the accessor's key/value contract rather than assuming `context.put("requestId", ...)` automatically populates MDC.

**Do not arbitrarily register multiple accessors operating on the same MDC.** `Slf4jThreadLocalAccessor`'s Javadoc recommends using it only when no other accessor simultaneously manages MDC or overlapping keys, such as tracing instrumentation. In Spring Boot/Micrometer Tracing apps, check which accessors the framework or tracing bridge already manages before adding another; if two accessors write/clear the same key, values may be overwritten or disappear unexpectedly.

If you only need logging in one callback, a manual `doOnEach` helper is usually easier to understand and has less global impact. Use an automatic MDC accessor when legacy imperative code genuinely needs to read MDC at many points across thread boundaries.

### 7.2. Creating an Accessor for a Legacy Library's Custom `ThreadLocal`

Suppose a legacy library reads the tenant from a `ThreadLocal` that the application can access through a wrapper:

```java
public final class LegacyTenantContext {
    private static final ThreadLocal<String> TENANT = new ThreadLocal<>();

    private LegacyTenantContext() {}

    public static String get() {
        return TENANT.get();
    }

    public static void set(String tenantId) {
        TENANT.set(tenantId);
    }

    public static void clear() {
        TENANT.remove();
    }
}
```

Accessor bridging that `ThreadLocal` with Reactor Context:

```java
import io.micrometer.context.ThreadLocalAccessor;

public final class TenantIdAccessor
        implements ThreadLocalAccessor<String> {

    public static final String KEY = "app.tenantId";

    @Override
    public Object key() {
        return KEY;
    }

    @Override
    public String getValue() {
        return LegacyTenantContext.get();
    }

    @Override
    public void setValue(String value) {
        LegacyTenantContext.set(value);
    }

    @Override
    public void setValue() {
        LegacyTenantContext.clear();
    }
}
```

Register once at application startup:

```java
ContextRegistry.getInstance()
        .registerThreadLocalAccessor(new TenantIdAccessor());

Hooks.enableAutomaticContextPropagation();
```

If using Spring Boot with `spring.reactor.context-propagation=auto`, let Boot enable automatic mode; do not call the hook again manually. The accessor still needs to be registered and the key in Reactor Context must match.

A service calling the blocking library can be written as:

```java
public Mono<Customer> findCustomer(String tenantId, String customerId) {
    return Mono.fromCallable(() ->
                    legacyClient.findCustomer(
                            LegacyTenantContext.get(), customerId))
            .subscribeOn(Schedulers.boundedElastic())
            .contextWrite(context ->
                    context.put(TenantIdAccessor.KEY, tenantId));
}
```

This is a **service pattern**, assuming `legacyClient.findCustomer` is a blocking call returning `Customer`. When the subscription executes on `boundedElastic`, automatic propagation restores the tenant `ThreadLocal` inside the publisher's callback from the subscription's Context.

Conditions for this to work:

1. The accessor is registered in the registry used by Context Propagation.
2. The key in `contextWrite` matches `TenantIdAccessor.KEY`.
3. Automatic mode is enabled before the subscription runs, or the callback sits inside an operator that supports restoration in `limited` mode.
4. The legacy call actually executes inside the restored scope, without spinning off onto an uninstrumented executor.
5. The no-arg `setValue()` must clear the `ThreadLocal`. Omitting this step can leak the previous request's tenant value into a later task on the same worker.

**Do not propagate a tenant merely because it happens to be in a controller thread's `ThreadLocal`.** Put the authenticated tenant into Reactor Context, and let the accessor provide a controlled bridge.

## 8. When External Libraries Create Their Own `ExecutorService`

Reactor's automatic propagation only controls boundaries instrumented by Reactor or its integrations. A library may create its own `ExecutorService`, thread pool, or callbacks. When code runs on those threads, Reactor does not automatically know to capture/restore Context.

Micrometer Context Propagation can wrap an executor to restore a snapshot per task. Conceptual example:

```java
ContextSnapshotFactory snapshotFactory =
        ContextSnapshotFactory.builder().build();

Mono<Result> result = Mono.deferContextual(contextView -> {
    ContextSnapshot snapshot =
            snapshotFactory.captureFrom(contextView);

    Executor contextAwareExecutor =
            snapshot.wrapExecutor(legacyExecutor);

    return Mono.fromFuture(
            CompletableFuture.supplyAsync(
                    legacyClient::call,
                    contextAwareExecutor));
});
```

This is **integration illustration code**, requiring declarations for `legacyExecutor`, `legacyClient`, and `Result`; the executor's lifecycle must be managed separately. `ContextSnapshotFactory` captures values from Reactor Context, and `wrapExecutor` wraps tasks to set `ThreadLocal`s during execution and restore the prior state when the task ends.

Another option is taking a snapshot and using `snapshot.setThreadLocals()` in a try-with-resources around a synchronous imperative block:

```java
try (ContextSnapshot.Scope ignored =
             snapshot.setThreadLocals()) {
    legacyLibrary.doWork();
}
```

**Never open a scope on one thread and close it on another.** The scope must be closed where it was opened to restore the previous `ThreadLocal` state properly. Never store a snapshot in a `static` field shared across requests; each subscription/task must carry its own snapshot.

If an external library has its own callback API, check whether it supports decorators, context carriers, or interceptors. Prefer the library's official integration; only wrap executors yourself once you clearly understand lifecycle, cancellation, exceptions, and shutdown.

## 9. Context Propagation Does Not Automatically Cross the Network

Both Reactor Context and `ThreadLocal` are scoped within a single JVM. They do not automatically turn into HTTP headers, message headers, or baggage sent to another service.

For example, `contextWrite(Context.of("requestId", "req-42"))` does not automatically cause outbound HTTP requests sent by `WebClient` to carry an `X-Request-Id` header. To propagate across the network, an explicit mechanism is needed:

- Use Micrometer Tracing/Observation and a compatible propagation format (typically W3C Trace Context) to carry trace/span info over HTTP.
- If the business needs a custom correlation ID, read it from Reactor Context and add the header in a `WebClient` filter or API client adapter.
- For Kafka/RabbitMQ, place metadata into message headers and read/restore it at the consumer boundary.
- Validate/verify externally received values; never treat client-sent request ID or tenant headers as proof of identity or authorization.

An illustrative `WebClient` filter showing how to read Reactor Context to add a correlation header:

```java
ExchangeFilterFunction requestIdFilter = (request, next) ->
        Mono.deferContextual(context -> {
            String requestId = context.getOrDefault(
                    "app.requestId", "unknown");

            ClientRequest updated = ClientRequest.from(request)
                    .header("X-Request-Id", requestId)
                    .build();

            return next.exchange(updated);
        });
```

This is an **illustrative configuration snippet** to be placed inside an appropriate `WebClient` configuration. In systems with Micrometer Tracing, prefer existing propagation instrumentation to avoid adding non-standard trace headers or generating trace IDs unlinked to spans.

## 10. MDC, Observation, and Tracing Are Not the Same Thing

Three related but distinct concepts:

- **MDC:** key/value fields for logging, typically backed by `ThreadLocal`.
- **Micrometer Observation:** describes an operation that can produce metrics and traces through registries/handlers.
- **Micrometer Tracing:** manages traces/spans and propagates trace context across processes.

A trace ID in logs may come from observation/tracing integration. You should not invent an arbitrary `traceId` in MDC and assume you have built valid distributed tracing. Distributed tracing also involves parent/child spans, trace IDs, sampling, baggage, propagation headers, and lifecycle.

Spring Boot Actuator/Observability uses Micrometer Observation and Context Propagation to carry observations across threads and reactive pipelines. When compatible instrumentation is present, log formatters can display trace/span IDs without manually writing an MDC bridge for each log statement. Even so, **custom request IDs or application metadata** still need to be put into Context and bridged explicitly if a library requires `ThreadLocal`.

Avoid overwriting keys managed by the tracing framework. If you want to add `tenantId` or `requestId`, use dedicated keys and make sure they do not conflict with existing accessors.

## 11. Limits and Costs of Enabling Automatic Propagation

Automatic mode is convenient, but it is not free:

1. **Overhead:** capturing/restoring `ThreadLocal`s incurs cost at every instrumented execution boundary. For pipelines with many operators and high event volume, benchmark it.
2. **Accessor coverage:** only `ThreadLocal`s with registered accessors are known how to read/set/clear. A library maintaining private state without an accessor will not propagate automatically.
3. **Executors outside Reactor:** a library's own thread pool must be wrapped/instrumented separately or use an official integration.
4. **Context missing a key:** automatic mode must clear/restore state when a key is absent from Context to avoid leaks; accessors must define reset properly.
5. **Multiple accessors for the same `ThreadLocal`:** they can overwrite or clear each other's state, especially when MDC is managed simultaneously by tracing and a custom accessor.
6. **Side effects and mutable context:** automatically propagating a mutable object does not make it thread-safe. Avoid sharing a mutable map across concurrent branches.
7. **Network boundaries:** automatic mode does not propagate data to other processes.
8. **Test isolation:** the hook is global state applying to new subscriptions; tests must initialize and clean up in a controlled manner rather than toggling randomly across parallel tests.

Use `limited` mode or a manual bridge when only a few log points are needed. Choose `automatic` mode when most of the application or libraries need `ThreadLocal` access across many operators and suitable accessors exist. Measure overhead on a representative workload before enabling it globally in a high-throughput system.

## 12. Testing Context and MDC

### 12.1. Testing Reactor Context with `StepVerifier`

The following test checks that a value written at the end of the chain can be read by an upstream operator:

File `src/test/java/demo/ReactorContextTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactorContextTest {

    @Test
    void contextWriteIsVisibleUpstream() {
        Mono<String> requestId = Mono.deferContextual(context ->
                Mono.just(context.get("app.requestId")))
                .contextWrite(context ->
                        context.put("app.requestId", "req-42"));

        StepVerifier.create(requestId)
                .expectNext("req-42")
                .verifyComplete();
    }
}
```

Requires JUnit Jupiter and `reactor-test` on the test classpath; run with `./gradlew test` or `mvn test` depending on your project. The test uses no `Thread.sleep` and does not depend on thread schedulers.

### 12.2. Verifying MDC Does Not Leak Between Two Subscriptions

In addition to testing Context, test MDC callbacks as follows:

- Subscription A has `requestId=A`; the log callback must read `A`.
- Subscription B has `requestId=B`; the log callback must read `B` even when the same worker is reused.
- A subscription without the key; the callback must not accidentally read leftover `A` or `B`.
- When a callback throws an exception, the MDC scope must still close via try-with-resources.
- With `publishOn` or `subscribeOn`, verify callbacks at the actual thread boundaries.
- When running tests in parallel, never use a static MDC value as a shared context source.

You can use a synchronized `List<String>` or a Logback test appender to capture logs. Do not assert fixed thread-name ordering since schedulers can choose different workers. Testing **context values and isolation** is the actual goal.

### 12.3. Testing Accessors for Legacy Libraries

For a custom `ThreadLocal` accessor, test all three operations:

1. `getValue()` reads the current thread's value accurately.
2. `setValue(value)` sets the value from the snapshot.
3. No-arg `setValue()` clears the `ThreadLocal` when Context lacks the key or the scope ends.

Test request A followed by request B on the same executor worker; after A, state must be restored/removed before B runs. Testing only on two brand-new threads can miss leak bugs.

For libraries with their own executors, integration tests must prove tasks actually run through the wrapped executor. A Reactor Context unit test does not prove a third-party thread pool picks up context automatically.

## 13. Common Mistakes and Fixes

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| MDC lost after `publishOn` | MDC is thread-bound and does not automatically follow the subscriber | Read Reactor Context and bridge at log points, or enable suitable propagation |
| MDC has the previous request's request ID | `ThreadLocal` was not cleared/restored | Use try-with-resources, accessor reset, and test worker reuse |
| `contextWrite` is present but `MDC.get` is still `null` | Context does not write to MDC automatically | Use a `doOnEach` helper or a Context Propagation accessor |
| `contextCapture` fails to capture the ID | `ThreadLocal` was cleared before subscription time, or accessor not registered | Check subscription timing and registry |
| Automatic mode has no effect | Hook enabled too late, Reactor/Context Propagation mismatch, missing accessor, or key absent from Context | Enable at startup, verify dependencies, keys, and accessors |
| `doOnNext` does not see MDC in `limited` mode | `limited` mode restores only in select operators like `handle`/`tap` | Use `tap`/`handle` or explicit MDC helper; consider `auto` mode |
| External library still does not see tenant | Library uses another `ThreadLocal` or its own executor | Write a suitable accessor and wrap the executor/callback |
| Context is right in service, but downstream HTTP receives no header | Internal context does not automatically cross the network | Use a `WebClient` filter, HTTP propagation, or message headers |
| Enabling MDC accessor makes trace ID disappear | Two accessors manage MDC simultaneously or overwrite the same key | Check tracing integration, select specific keys, avoid duplicate registration |
| Logs have trace ID, but metrics cardinality spikes | Putting unique IDs into metric tags | Keep trace/request IDs in logs/traces; use low-cardinality tags for metrics |
| Security context lost after thread switch | Not using Spring Security's propagation mechanism or unsupported context boundary | Use official integration and test principal in the right callback |
| Unit tests pass, yet production still leaks | Thread pool reuse, external executors, cancellation, or concurrent requests untested | Write integration/load tests with multiple requests and reused workers |

## 14. Implementation Checklist

1. **Identify data to propagate:** request ID, trace/span, tenant, locale, or security principal; do not dump all state into one `ThreadLocal`.
2. **Prefer Reactor Context:** use `contextWrite` to write and `deferContextual` to read.
3. **Choose MDC points carefully:** logging in `doOnEach` can be bridged manually via `MDC.putCloseable`; no need to restore MDC on every business operator.
4. **Check versions:** Reactor 3.5.0 introduced Context Propagation SPI; 3.5.3 added the automatic hook; Spring Boot 3.2+ provides `spring.reactor.context-propagation`.
5. **Choose `limited` vs. `auto`:** understand which callbacks are restored and the cost before enabling globally.
6. **Register accessors exactly once:** pick specific keys and do not clash with tracing or security accessors.
7. **Ensure cleanup:** `MDC.MDCCloseable`, `Scope.close`, and `ThreadLocal.remove` must run even on exceptions.
8. **Wrap external executors:** do not assume every thread pool is managed by Reactor.
9. **Separate process boundaries:** use HTTP/message propagation for data crossing the network.
10. **Protect data:** do not put tokens/PII into MDC; do not use high-cardinality IDs as metric tags.
11. **Test concurrency and worker reuse:** concurrent requests, missing-key requests, errors, cancellation, external executors.
12. **Measure performance:** compare `limited`/`auto`/manual bridging under realistic load and monitor p95/p99, allocations, and log volume.

## 15. References

- [Project Reactor Reference – Context Propagation](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html): `Context`, `contextWrite`, `contextCapture`, `limited` and `automatic` modes.
- [Project Reactor Reference – Contextual Logging (MDC)](https://docs.spring.io/projectreactor/reactor-core/docs/current/reference/html/#faq.mdc): `doOnEach`, `Signal.getContextView`, and `MDC.MDCCloseable` pattern.
- [Spring Boot – Observability / Context Propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html): `spring.reactor.context-propagation` property and `ContextPropagatingTaskDecorator`.
- [Micrometer Context Propagation – Purpose](https://docs.micrometer.io/context-propagation/reference/purpose.html): `ThreadLocalAccessor`, `ContextSnapshot`, `ContextRegistry`, and imperative/reactive boundaries.
- [Micrometer Context Propagation – Usage Examples](https://docs.micrometer.io/micrometer/reference/1.12/contextpropagation/usage.html): registering accessors and restoring `ThreadLocal`s with scopes.
- [Slf4jThreadLocalAccessor Javadoc](https://javadoc.io/doc/io.micrometer/context-propagation/latest/io/micrometer/context/integration/Slf4jThreadLocalAccessor.html): bridging MDC, key selection, and caveats when multiple accessors manage MDC.
- [SLF4J MDC API](https://www.slf4j.org/api/org/slf4j/MDC.html): MDC operations and `MDCCloseable`.

## 16. Takeaway

**Reactor Context is the subscription-scoped context source; MDC and `ThreadLocal` are temporary thread-bound state.** Never assume they stay synchronized automatically when a pipeline switches threads.

For reactive code you control, store metadata with `contextWrite` and read it with `deferContextual`. When logging is needed, obtain Context from `Signal`, set MDC in a short scope via `MDC.putCloseable`, and close the scope. When you must invoke `ThreadLocal`-based imperative libraries, use Micrometer Context Propagation and appropriate accessors; for custom executors, wrap tasks/executors to capture and restore context.

Automatic propagation is convenient, yet it only works for registered keys/accessors and subscriptions created after configuration is enabled. It does not transmit data over the network, does not replace security/tracing integrations, and does not eliminate the need for cleanup. Designing boundaries properly ensures logs carry the right request ID, legacy libraries receive the right metadata, and thread pools do not carry one request's context into the next.
