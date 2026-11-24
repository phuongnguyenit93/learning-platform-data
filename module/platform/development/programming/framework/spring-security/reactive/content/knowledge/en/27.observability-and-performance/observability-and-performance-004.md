# Connecting Reactor Context with Observability, Tracing, and Controlled MDC

## Learning Objectives

After this lesson, you will be able to: (1) explain why `ThreadLocal`/MDC does not automatically follow a WebFlux processing flow; (2) write and read per-*subscription* data using Reactor `Context`; (3) distinguish an application correlation ID from trace ID/span ID and Spring Security reactive's `SecurityContext`; (4) use Micrometer Observation/Tracing to observe pipelines without leaking data; (5) populate MDC with only select safe values within a callback scope and restore prior state afterward; (6) verify context propagation across schedulers, concurrent requests, and error branches.

**Context:** Spring Security runs on Spring WebFlux, using asynchronous programming with `Mono`/`Flux`; Java examples use Java 17+. The Spring integration snippets belong inside an existing Spring Boot WebFlux application, while the `ContextDemo` example below is a standalone program.

## 1. Why Is Reactor Context Needed?

Suppose `GET /orders/42` passes through the security filter, calls a service, makes an HTTP call to an inventory service, and logs the outcome. In the traditional servlet model, many libraries store per-request data in `ThreadLocal`. In WebFlux, a request can switch from an event-loop thread to another thread upon `publishOn`, timers, I/O, or callbacks; conversely, one thread can serve many requests. Therefore, using thread ID to infer the request or keeping `MDC.put(...)` across the entire chain is unsafe.

Three concepts serve distinct purposes:

| Component | What Is It For? | Boundaries/Notes |
| --- | --- | --- |
| Reactor `Context` / `ContextView` | Carries small, immutable data per *subscription*: requestId, correlation keys, security/observability context stored by libraries | Bound to the subscriber, not the thread; follows Reactor chains that preserve context |
| Micrometer `Observation` and tracing | Measures duration, outcome, creates/links spans and traces across services | Requires instrumentation, tracer bridge, and appropriate exporter; not every value in Reactor Context automatically becomes a span |
| SLF4J MDC | Adds fields to a log line such as `traceId`, `spanId`, `requestId` | Thread-bound state of the logging backend; must be restored/cleared after its usage scope |
| Spring Security `ReactiveSecurityContextHolder` | Retrieves `Authentication` for the reactive flow | Uses Reactor Context; avoid reading user from Servlet-style `SecurityContextHolder` |

**Distinguishing IDs:** `requestId` is an application-defined correlation key; `traceId` identifies a distributed trace, while `spanId` identifies an operation within a trace. Do not assign `requestId` as `traceId` or fabricate fake traces from an arbitrary header. A request may carry all three, but they have different lifecycles and trust levels.

Typical flow diagram:

```text
HTTP request
  -> WebFilter: validate/normalize X-Request-ID
  -> contextWrite: add app.requestId to Reactor Context
  -> Spring Security: provide Reactive SecurityContext
  -> Controller/Service: deferContextual + getContext
  -> Observation/Tracing: record duration, status, span
  -> logger: read Context then bind MDC right when writing a line
  -> HTTP response: return chosen requestId (if policy allows)
```

## 2. How Reactor Context Propagates

`Context` is an immutable structure: `put` returns a new context without mutating the old object. `contextWrite(...)` provides context to operators **above it when subscription occurs**; `Mono.deferContextual(...)`/`Flux.deferContextual(...)` reads context at subscription time, rather than reading a global variable when building the pipeline. Context propagates across `publishOn` and `subscribeOn` in standard Reactor pipelines, even when threads change.

Standalone example. Create two files:

```groovy
// build.gradle
plugins {
    id 'java'
    id 'application'
}
repositories {
    mavenCentral()
}
dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.7'
}
application {
    mainClass = 'demo.ContextDemo'
}
```

```java
// src/main/java/demo/ContextDemo.java
package demo;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.util.context.Context;

public final class ContextDemo {
    public static void main(String[] args) {
        var values = Flux.just("A", "B")
                .publishOn(Schedulers.parallel())
                .concatMap(item -> Mono.deferContextual(ctx ->
                        Mono.just(item + ": " + ctx.<String>get("requestId"))))
                .contextWrite(Context.of("requestId", "req-42"))
                .collectList()
                .block();

        System.out.println(values);
    }
}
```

Run `gradle run` (or `./gradlew run` if the project has a Gradle wrapper). Output printed by the program:

```text
[A: req-42, B: req-42]
```

`concatMap` preserves the order A then B; `publishOn` switches downstream processing to a scheduler, yet `requestId` remains available because it belongs to the subscription. `block()` here is only for running the example from `main`; **never call `block()` inside a WebFlux request handler**. Placing `contextWrite` above `deferContextual` prevents the reader from seeing the key because context flows from downstream to upstream. Two separate `subscribe()` calls are two separate subscriptions; do not use a shared mutable variable to share context between requests.

## 3. Setting requestId Safely in Spring WebFlux

A `WebFilter` can determine the request ID at the HTTP boundary, allowlist selected characters, and put it into Reactor Context for inner processing:

```java
// RequestIdWebFilter.java - located in a Spring-scanned package
import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public final class RequestIdWebFilter implements WebFilter {
    public static final String KEY = "app.requestId";
    private static final Pattern SAFE =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        String incoming = exchange.getRequest().getHeaders()
                .getFirst("X-Request-ID");
        String requestId = incoming != null && SAFE.matcher(incoming).matches()
                ? incoming
                : UUID.randomUUID().toString();

        exchange.getResponse().getHeaders().set("X-Request-ID", requestId);
        return chain.filter(exchange)
                .contextWrite(ctx -> ctx.put(KEY, requestId));
    }
}
```

Explanation:

1. Values coming from the client are **untrusted input**: the regex above rejects newlines and control characters; length should be bounded. If you do not trust the header source, always generate a new ID at the trusted boundary instead of reusing the client's ID. Never use this ID as proof of authentication.
2. Each `filter` invocation creates its own `requestId`. `contextWrite` does not mutate shared state; concurrent requests never contend over a static variable.
3. The filter can set the response header before returning `Mono<Void>`; only echo back a validated opaque ID. Depending on architecture, a reverse proxy/API gateway may be responsible for generating the ID.
4. When accessing from code outside the original pipeline (external callbacks, `new Thread(...)`, manually created `CompletableFuture`), propagate data/context explicitly; do not assume Context automatically crosses every API.

In a service or controller, read the ID at subscription time:

```java
import reactor.core.publisher.Mono;

public Mono<String> currentRequestId() {
    return Mono.deferContextual(ctx ->
            Mono.just(ctx.getOrDefault(RequestIdWebFilter.KEY, "missing")));
}
```

This is an **illustrative method inside a bean/service**, not a standalone Java file. Do not use `ThreadLocal` to store the request ID; do not call `subscribe()` manually in a controller as that detaches the subscription lifecycle and loses WebFlux error handling/cancellation.

## 4. Preserving Spring Security Reactive Context Properly

Spring Security WebFlux uses `ReactiveSecurityContextHolder` to read `SecurityContext` from Reactor Context. Example when retrieving the principal name **inside an authenticated flow**:

```java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

public Mono<String> currentPrincipalName() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> auth.getName())
            .defaultIfEmpty("anonymous");
}
```

This is also an illustrative method to place inside an application component. `defaultIfEmpty` handles the case when no SecurityContext is present; if Spring Security creates an `AnonymousAuthenticationToken`, the principal name may be `anonymousUser`. Actual access permissions must be decided by authorization configuration, not by checking whether a name string equals `anonymous`.

In a WebFlux application configured with Spring Security, security filters normally populate the context for the pipeline; in unit tests, you can use `.contextWrite(ReactiveSecurityContextHolder.withAuthentication(authentication))` to supply a test authentication object. **Never extract tokens, passwords, cookies, personally identifiable information, or the entire `Authentication` object and place them into MDC, metrics tags, trace attributes, baggage, or response headers.** When business logging is required, log only policy-approved safe state; having a `requestId` grants no additional access privileges.

## 5. Connecting Observation and Distributed Tracing

In a Spring Boot WebFlux application using Actuator, Micrometer Observation provides the model for measuring HTTP operations; Micrometer Tracing (when a bridge is present) maps observations to spans to join a distributed trace. Illustrative Gradle dependencies in an application **using the Spring Boot BOM for version management**:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
    implementation 'io.projectreactor:reactor-core-micrometer'
    testImplementation 'io.projectreactor:reactor-test'
}
```

You must configure an OTLP exporter/collector appropriate for the environment. Example sampling configuration for a test or low-traffic deployment:

```yaml
management:
  tracing:
    sampling:
      probability: 0.1
```

`0.1` is a 10% sampling rate; adjust based on load, observability goals, and cost. Enable 100% sampling in test environments when inspecting individual requests, and do not assume that is a production setting. Tracing requires a tracer bridge; adding Actuator alone does not mean all traces will be exported. When Micrometer Tracing is active, Spring Boot can include `traceId` and `spanId` in log correlation output. There is no need to synthesize these values manually from `X-Request-ID`.

For a specific pipeline you want to observe individually, Reactor provides `tap` with `Micrometer.observation` from `reactor-core-micrometer`:

```java
// Integration snippet inside a service with repository and observationRegistry
import reactor.core.observability.micrometer.Micrometer;

return repository.findById(orderId)
        .name("orders.find")
        .tap(Micrometer.observation(observationRegistry));
```

When the publisher is subscribed to, the listener manages the observation lifecycle across complete/error/cancel signals. Never measure an asynchronous `Mono` by opening an `Observation.Scope` on the current thread, returning the `Mono`, and immediately closing the scope: the actual work has not run yet. Use Reactor-aware instrumentation or subscription-bound lifecycles; do not create a span per element when you only need to measure the request or main operation.

When making outbound HTTP calls, use the Spring Boot auto-configured `WebClient.Builder` to get proper observation/tracing customizations and propagation. Example:

```java
// Spring component; builder is injected via constructor
this.webClient = builder.baseUrl("https://inventory.example").build();
```

Do not casually call `WebClient.create(...)` and expect automatic trace propagation identical to Boot's configuration. Standard trace HTTP headers like `traceparent` should be managed by instrumentation according to your system's trust policy; application request IDs can be separate headers if permitted.

Regarding tags: `method=GET`, `route=/orders/{id}`, `outcome=SUCCESS` have finite value domains and are suitable as **low-cardinality tags** for metrics. Order IDs, user IDs, and full URLs have unbounded variation and are **high-cardinality**; do not push them as metric tags because they cause time-series explosion. Even when attaching a high-cardinality value to a trace span, evaluate privacy and retention policies.

## 6. Controlled MDC: Set Only Within the Logging Scope

MDC is a `ThreadLocal` managed by the logging backend, so avoid this anti-pattern:

```java
// Anti-pattern: DO NOT use in a reactive WebFilter
MDC.put("requestId", requestId);
return chain.filter(exchange);
```

MDC is set on the thread executing the filter, while downstream callbacks may run on different threads; leftover values can contaminate other requests reusing that thread. A safe manual technique when logging a signal is to **read Reactor Context inside the callback, set MDC, log, and restore the previous value in a `finally` block**:

```java
// SafeMdcLogger.java - utility in the same package as RequestIdWebFilter
import java.util.function.Consumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import reactor.core.publisher.Signal;

public final class SafeMdcLogger {
    private static final Logger LOG =
            LoggerFactory.getLogger(SafeMdcLogger.class);

    private SafeMdcLogger() {}

    public static <T> Consumer<Signal<T>> logOnNext(String event) {
        return signal -> {
            if (!signal.isOnNext()) {
                return;
            }
            String requestId = signal.getContextView()
                    .getOrDefault(RequestIdWebFilter.KEY, "missing");
            String previous = MDC.get("requestId");
            try {
                MDC.put("requestId", requestId);
                LOG.info("event={} resultReceived=true", event);
            } finally {
                if (previous == null) {
                    MDC.remove("requestId");
                } else {
                    MDC.put("requestId", previous);
                }
            }
        };
    }
}
```

Apply it on a pipeline, for example `repository.findById(id).doOnEach(SafeMdcLogger.logOnNext("order-read"))`. With Logback, the log pattern must include `%X{requestId}` for this MDC field to appear as text; if using structured logging, configure the encoder per your current stack. Setting `MDC` inside a synchronous callback like above only ensures the right value **while that callback executes**—it does not make `MDC` propagate across the entire request. Do not invoke asynchronous operations inside `try` expecting MDC to stay intact on another thread.

If logs do not require MDC-based formatting, a simpler solution is passing the ID as an explicit log parameter: `log.info("requestId={} action=read", requestId)`. This avoids ThreadLocal manipulation overhead. Avoid logging full payloads, bearer tokens, or `SecurityContext` when debugging.

### Automatic Context Propagation with Micrometer

Reactor integrates with `io.micrometer:context-propagation`. In **default mode**, restoring `ThreadLocal` from Reactor Context is supported in certain operators (notably `handle`/`tap`) when corresponding accessors exist; do not assume every callback automatically has MDC populated. `contextCapture()` captures `ThreadLocal`s with registered accessors into Reactor Context at subscription time.

If the system genuinely needs automatic switching between Reactor Context and registered `ThreadLocal`s, you can enable it early at startup:

```java
import reactor.core.publisher.Hooks;

// Call at startup, before any application subscriptions:
Hooks.enableAutomaticContextPropagation();
```

This mode requires the `context-propagation` library and corresponding `ThreadLocalAccessor`s; the hook **only affects subscriptions created after it is enabled**. It does not automatically turn every key like `app.requestId` into MDC: you need proper accessors/mapping strategies and must avoid registering duplicates alongside Boot-managed instrumentation. Restoration mechanisms must also clear state when a key is absent to prevent leaks. Because global hooks can add overhead and affect library behavior, prefer Spring Boot/Micrometer-configured propagation, test before adding manual hooks, and compare throughput/latency.

## 7. Behavior Testing and QA

With `reactor-test`, verify data survives an asynchronous boundary:

```java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

class ReactorContextTest {
    @Test
    void requestIdSurvivesAsyncBoundary() {
        Mono<String> pipeline = Mono.delay(Duration.ofMillis(5))
                .flatMap(tick -> Mono.deferContextual(ctx ->
                        Mono.just(ctx.<String>get("requestId"))))
                .contextWrite(Context.of("requestId", "req-test"));

        StepVerifier.create(pipeline)
                .expectNext("req-test")
                .verifyComplete();
    }
}
```

Required integration-level tests:

1. **Two concurrent requests:** assign IDs A and B, perform `publishOn`, and call downstream; each log line contains only its corresponding request's ID, with no ID from the prior request appearing on a reused thread.
2. **Error/cancel paths:** trigger `onError`/cancellation; observations complete with the proper lifecycle; manual MDC still restores via `finally`; headers/IDs do not leak into subsequent requests.
3. **Security:** call endpoints with and without authentication; `ReactiveSecurityContextHolder` enforces 401/403 policies; `Authentication` is not read from Servlet `SecurityContextHolder`.
4. **Tracing:** call an endpoint through Boot's `WebClient.Builder`, verify traces have parent/child spans and log correlation per configuration; note that sampling/exporter issues can prevent traces from reaching the collector.
5. **Invalid headers:** test long values, newlines, and odd characters; they must be replaced with a new ID. Never log untrusted headers directly.
6. **Performance:** compare log counts, p95/p99 latency, and CPU with extra MDC scopes or automatic propagation enabled vs. disabled. Avoid logging every element of a high-rate `Flux` when only aggregate observation is needed.

### Troubleshooting Table

| Symptom | Common Cause | How to Check/Fix |
| --- | --- | --- |
| `deferContextual` lacks `requestId` | `contextWrite` placed in the wrong position, new subscription created outside pipeline, or context lost at external API | Check operator order; add ID downstream of the reader; pass context explicitly across external boundaries |
| MDC correct at request start but wrong after `publishOn` | MDC is thread-bound, not propagated across schedulers | Set MDC only at log time and restore; or use configured propagation and test on real schedulers |
| Logs have `requestId` but lack `traceId` | No active tracing bridge/observation, missing log pattern, or missing scope | Check dependencies, instrumentation, logging, and sampling config; do not fix by fabricating fake traceIds |
| Collector shows no spans | Wrong exporter/endpoint, low sampling, network or collector error | Check exporter config, confirm spans are created and backend connectivity works |
| Request B shows Request A's ID | MDC not cleared/restored, mutable/global variable, or scope held too long | Find `MDC.put` without `finally`, remove global state, and add concurrency tests |
| Metrics have too many series | Using userId/orderId/raw URL as metric tags | Use low-cardinality route template/status/operation; move rich details to controlled logs/traces |

## 8. Key Takeaways

- Treat **Reactor Context as the per-subscription data source**; read with `deferContextual`, write with `contextWrite`, independent of threads.
- Let **Spring Security** manage authentication context via `ReactiveSecurityContextHolder`; never copy authentication objects or tokens into observability systems.
- Let **Micrometer Observation/Tracing** manage spans, trace propagation, sampling, and exporters. An application correlation ID is a log lookup key, not a substitute for distributed tracing.
- Use **short-lived MDC**, restoring prior state in `finally`; if you just need to log a value, pass it as an explicit log parameter. Never let MDC persist across async boundaries.
- Measure instrumentation cost, control cardinality and sensitive data; test concurrency, error/cancel paths, HTTP boundaries, schedulers, and outbound HTTP before broad rollout.

## Official Documentation

- Reactor Context Propagation: https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html
- Reactor Micrometer instrumentation: https://projectreactor.io/docs/core/release/reference/metrics.html
- Spring Security `ReactiveSecurityContextHolder`: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Boot Actuator Tracing: https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html
- Micrometer Observation: https://docs.micrometer.io/micrometer/reference/observation/introduction.html
