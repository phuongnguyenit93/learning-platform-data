# Reactor Context and How It Differs from ThreadLocal

## Learning Objectives

After this lesson, you can:
- Explain why processing-flow data (such as trace IDs, tenant IDs, and authentication info) should not rely by default on `ThreadLocal` in reactive applications.
- Describe `reactor.util.context.Context`, `ContextView`, `Subscriber`-scoped visibility, and context propagation direction on subscribe.
- Use `contextWrite(...)` and `deferContextual(...)` and read the right context scope, even across scheduler switches or `flatMap`.
- Relate Reactor Context to Spring Security WebFlux's `ReactiveSecurityContextHolder`; recognize when a bridge to `ThreadLocal`-based libraries is needed.

## 1. Problem: One Request Does Not Mean One Thread

In synchronous Servlet-style programs, the same thread typically handles a request segment from start to finish. Developers can put `requestId` into a `ThreadLocal` and retrieve it in the service layer without passing parameters through every function. However, this approach binds data to a **physical thread**, not to the **logical request**.

In Reactor, a `Mono` or `Flux` can execute across multiple threads due to `publishOn`, `subscribeOn`, asynchronous sources, or I/O operations. Meanwhile, a single event-loop thread can serve many different subscriptions over time. Therefore:

- Setting a value in `ThreadLocal` on thread A does not guarantee a callback on thread B can read that value.
- If using a thread pool and forgetting `remove()`, a later task on the same thread may see stale state.
- Even when steps happen to run on the same thread, that is not a contract guaranteeing pipeline correctness.

Reactor Context solves the problem of propagating **metadata bound to the reactive processing flow** without stuffing it into the business payload `T` of `Mono<T>`/`Flux<T>`.

## 2. What Is Reactor Context Really?

`reactor.util.context.Context` is a structurally immutable **key → value** map structure. `ContextView` is its read-only interface. Data is usually stored under `String` keys or dedicated object keys; values can be arbitrary objects, though they should be small, semantically clear, and safe to share.

Core points:

1. **Bound to the Subscriber, not the Thread.** Context is part of the subscription relationship; Reactor passes it through the operator chain during subscribe. A single publisher can be subscribed to multiple times with different contexts.
2. **Written at subscription time.** `contextWrite` receives the context from downstream and creates a new context for the upstream portion of that operator. `Context.put`/`delete` return new instances; they do not mutate the old context in place.
3. **Subscription signals flow bottom-up; data usually flows top-down.** In a chain written top-to-bottom, a `contextWrite` placed further down can supply data to a `deferContextual` placed earlier.
4. **Scope is determined by operator position.** Operators downstream of a `contextWrite` do not automatically see that operator's new write. When the same key is written multiple times, the write closer to the reader along the upstream branch determines the value the reader sees.
5. **Map immutability does not make value objects immutable.** Do not use Context as a holder for mutable state that requires synchronization.

Visual model:

~~~text
Pipeline assembly:              Mono.deferContextual(...).map(...).contextWrite(...)
Subscribe/context:              subscriber -> contextWrite -> map -> deferContextual
OnNext data:                    deferContextual -> map -> subscriber
~~~

There is no global `Context` shared across all requests. You cannot simply call `Context.of(...)` and expect other execution flows to see it automatically; it must be attached to a **specific subscription**.

## 3. Comparison with ThreadLocal

| Criterion | `ThreadLocal<T>` | Reactor `Context` |
|---|---|---|
| Data attachment unit | One Java thread | Subscriber/subscription in a Reactor chain |
| Write/read | `set/get/remove` | `contextWrite` / `deferContextual`, `ContextView` |
| Thread switch via scheduler | Does not automatically preserve value | Context continues to propagate within a proper Reactor chain |
| Direction and scope | Statements running on the current thread | Readers upstream of the corresponding `contextWrite` operation |
| Lifecycle | Until `remove()` or thread termination | Tied to the subscription and its inner branches |
| Common risks | Context lost on thread switch; state leaked on thread pool if uncleaned | Misplaced `contextWrite`; lost scope when creating an independent subscription |
| Spring Security usage | Thread-bound `SecurityContextHolder` in imperative model | `ReactiveSecurityContextHolder` using Reactor Context in WebFlux |

**Do not misunderstand:** `ThreadLocal` can still be bridged with reactive pipelines via configured context propagation mechanisms. The difference is that Reactor Context has a subscriber-based scoping model, whereas raw `ThreadLocal` has a thread-based model.

## 4. Key APIs and Read/Write Direction

### 4.1. Writing metadata with contextWrite

~~~java
Mono<String> task = Mono.deferContextual(view ->
    Mono.just("traceId=" + view.<String>get("traceId"))
).contextWrite(context -> context.put("traceId", "req-123"));
~~~

`contextWrite(Function<Context, Context>)` creates a new context so **upstream** operators see the `traceId` value. There is also a `contextWrite(ContextView)` overload, convenient when you already have a context to merge:

~~~java
Mono<String> task = Mono.deferContextual(view ->
    Mono.just(view.getOrDefault("locale", "vi").toString())
).contextWrite(Context.of("locale", "en"));
~~~

`Context.of(key, value)` creates a new map; `put`, `putAll`, and `delete` return new contexts. You neither need nor should expect to call `set` on a Context.

### 4.2. Reading metadata with deferContextual

`Mono.deferContextual(view -> ...)` (similar to `Flux.deferContextual`) executes its lambda only within a subscription's context. Use `view.get(key)` when the key is **required**; if missing, reading raises an error. Use `getOrDefault(key, fallback)` or `hasKey(key)` when metadata may be absent.

If you need context alongside an element of a pipeline, you can place `deferContextual` inside `flatMap`:

~~~java
Mono<String> result = Mono.just("order-7")
    .flatMap(orderId -> Mono.deferContextual(view ->
        Mono.just(orderId + "@" + view.getOrDefault("tenantId", "public"))
    ))
    .contextWrite(Context.of("tenantId", "tenant-a"));
~~~

The result is `order-7@tenant-a`. `Mono.just(...)` by itself provides no API to read Context; read it where needed using an operator that supports contextual access.

### 4.3. Position of contextWrite changes the outcome

~~~java
Mono<String> visible = Mono.deferContextual(view ->
    Mono.just(view.getOrDefault("key", "missing").toString())
).contextWrite(Context.of("key", "visible"));  // "visible"

Mono<String> invisible = Mono.just("start")
    .contextWrite(Context.of("key", "hidden"))
    .flatMap(s -> Mono.deferContextual(view ->
        Mono.just(view.getOrDefault("key", "missing").toString())
    ));                                         // "missing"
~~~

In the second example, `flatMap` sits **downstream** of `contextWrite`, so the inner publisher reads the downstream subscriber's context and does not receive the `hidden` write above it. This is a common mistake when reading a pipeline as if it were sequential statements.

## 5. Standalone Runnable Java 17 Example

Create a small Java Gradle project. The example below uses Reactor Core 3.8.7 (Java 17+), without automatic ThreadLocal integration enabled.

File `build.gradle`:

~~~groovy
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

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'ReactorContextDemo'
}
~~~

File `src/main/java/ReactorContextDemo.java`:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.util.context.Context;

public class ReactorContextDemo {
    private static final ThreadLocal<String> TENANT = new ThreadLocal<>();

    public static void main(String[] args) {
        TENANT.set("tenant-a");

        String threadLocalValue = Mono.fromSupplier(() -> {
                String value = TENANT.get();
                return value == null ? "<null>" : value;
            })
            .subscribeOn(Schedulers.parallel())
            .block();
        System.out.println("ThreadLocal=" + threadLocalValue);

        Mono<String> preserved = Mono.deferContextual(view ->
                Mono.just("tenant=" + view.<String>get("tenantId")))
            .publishOn(Schedulers.parallel())
            .contextWrite(Context.of("tenantId", "tenant-a"));
        System.out.println(preserved.block());

        Mono<String> scope = Mono.deferContextual(view ->
                Mono.just("upstream=" + view.getOrDefault("key", "none")))
            .contextWrite(ctx -> ctx.put("key", "inner"))
            .flatMap(value -> Mono.deferContextual(view ->
                Mono.just(value + ", downstream=" +
                    view.getOrDefault("key", "none"))))
            .contextWrite(Context.of("key", "outer"));
        System.out.println(scope.block());

        Mono<String> reusable = Mono.deferContextual(view ->
            Mono.just("request=" + view.<String>get("requestId")));
        System.out.println(
            reusable.contextWrite(Context.of("requestId", "r1")).block());
        System.out.println(
            reusable.contextWrite(Context.of("requestId", "r2")).block());

        TENANT.remove();
    }
}
~~~

Run command from the project directory (with Gradle Wrapper):

~~~bash
./gradlew run --quiet
~~~

On Windows use `gradlew.bat run --quiet`; if no wrapper is present but Gradle is installed, use `gradle run --quiet`.

Expected stdout:

~~~text
ThreadLocal=<null>
tenant=tenant-a
upstream=inner, downstream=outer
request=r1
request=r2
~~~

Line-by-line explanation:

- `TENANT.set` runs on the main thread; `subscribeOn(Schedulers.parallel())` moves reading `ThreadLocal` to another thread where that thread's `TENANT` has not been set.
- `publishOn` changes where signals are processed, yet `tenantId` remains accessible via Reactor Context.
- `contextWrite("outer")` supplies context to `flatMap`; `contextWrite("inner")` sits closer to the source and overrides the key for the upstream reader. The reader inside `flatMap` sees `outer`.
- Two subscriptions to the `reusable` publisher receive different `requestId` values; there is no mutation of a shared context variable.

`block()` is only present to demonstrate a console application. **In a WebFlux controller/service handling a reactive request, return `Mono`/`Flux` and avoid calling `block()`**: besides blocking a thread, `block()` creates a separate subscription and can lose the expected context.

## 6. Scope in Inner Branches, Multiple Subscriptions, and Schedulers

**A Publisher is not a subscription.** A reusable `Mono<String>` can serve many requests; values in Reactor Context are normally supplied when each request subscribes. Do not attach request data to a mutable singleton field instead.

**`flatMap` creates an inner publisher.** The current context can be used by the Reactor inner branch when subscribed to by the operator; however, a `contextWrite` placed *inside* an inner branch affects only the upstream portion of that branch, not the entire outer chain's context. Example:

~~~java
Mono<String> flow = Mono.just("item")
    .flatMap(item ->
        Mono.deferContextual(view ->
            Mono.just(item + ":" + view.<String>get("scope")))
        .contextWrite(Context.of("scope", "inner"))
    )
    .flatMap(value ->
        Mono.deferContextual(view ->
            Mono.just(value + ":" + view.<String>get("scope"))))
    .contextWrite(Context.of("scope", "outer"));
// item:inner:outer
~~~

**`publishOn`/`subscribeOn` by themselves do not erase Reactor Context.** However, when leaving the Reactor chain via arbitrary callbacks, manually calling `subscribe()`, spawning tasks on an unbridged `Executor`, or switching to an API that does not manage Reactor Context, you can create a new subscription/context boundary. To preserve semantics, prefer **returning publishers and composing with operators** (`flatMap`, `then`, `zipWhen`, ...) instead of manually subscribing inside a service.

## 7. Direct Connection to Spring Security WebFlux

In synchronous Servlet applications, the default `SecurityContextHolder` is typically backed by `ThreadLocal`. In reactive applications, Spring Security must resolve the right `Authentication` per subscriber even when multiple requests share an event-loop thread. Therefore, Spring Security provides `ReactiveSecurityContextHolder` to store/read `Mono<SecurityContext>` in Reactor Context.

Methods to remember:

- `ReactiveSecurityContextHolder.getContext()`: returns `Mono<SecurityContext>` for the current subscription; when no context exists, the publisher can be empty.
- `ReactiveSecurityContextHolder.withAuthentication(authentication)`: creates a `Context` holding a new security context with the provided `Authentication`.
- `ReactiveSecurityContextHolder.withSecurityContext(Mono<? extends SecurityContext>)`: creates a `Context` from a security context publisher.
- `ReactiveSecurityContextHolder.clearContext()`: returns a function that removes the security context entry from Reactor Context for the corresponding upstream scope.

In WebFlux configured with Spring Security, web filters authenticate/restore the context for the request flow; applications normally **read** the current context rather than constructing an `Authentication` themselves to impersonate a real user.

Example method in a Spring WebFlux service (integration snippet; requires Spring Security reactive dependencies compatible with the application's Spring Boot version):

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

public Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .defaultIfEmpty("anonymous");
}
~~~

This `Mono` must be subscribed **within a request flow that has passed through the Spring Security filter chain**. Paths with security rules blocking unauthenticated requests can return HTTP 401/403 before the method runs; the `"anonymous"` value is only a publisher-level fallback and does not make an endpoint public.

When writing unit tests for a service, you can supply a test `Authentication` within the same subscription:

~~~java
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Authentication testUser =
    new TestingAuthenticationToken("alice", "unused", "ROLE_READER");

Mono<String> tested = ReactiveSecurityContextHolder.getContext()
    .map(security -> security.getAuthentication().getName())
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(testUser));

// tested emits "alice" when subscribed.
~~~

This is a demonstration of intentional testing/context injection, **not an actual login operation**. Clearing the entry with `clearContext()` is also not equivalent to revoking a JWT, deleting a session, or performing a full logout workflow. Do not use imperative `SecurityContextHolder.getContext()` to infer request identity inside a reactive pipeline.

## 8. What If a Library Still Requires ThreadLocal/MDC?

Logging MDC, tracing, or legacy code libraries may rely on `ThreadLocal`. Reactor Context **does not automatically copy every key into every ThreadLocal**. There are two approaches:

1. **Prefer reactive/context-aware APIs** if the library supports them: keep the correlation ID in Context and read it at the appropriate operator, or pass metadata as explicit parameters when entering business APIs.
2. **Use a configured bridge**, such as Micrometer Context Propagation. Reactor Core supports `contextCapture()` to snapshot `ThreadLocal` values that have registered `ThreadLocalAccessor`s at subscription time, and `Hooks.enableAutomaticContextPropagation()` for automatic ThreadLocal restoration on new subscriptions. Appropriate dependencies/accessor registrations must be present; enable the hook early at application startup and measure actual performance overhead.

Default (limited) mode and automatic mode differ in how extensively `ThreadLocal` values are restored. Do not assume `publishOn` automatically restores MDC, nor assume `contextCapture()` can capture variables without a registered accessor. If you use `ThreadLocal` directly to interact with an external library, be sure to restore and clear state reliably, especially on thread pools.

Reactor Context is a **per-subscriber data source**; a bridge is only a way to integrate with APIs having a thread-bound contract. For authentication information in WebFlux, prefer Spring Security's reactive mechanisms.

## 9. Practical Design and Common Mistakes

**Appropriate data:** trace/correlation IDs, verified tenant IDs, library metadata, and framework-managed security context. Use Context only for auxiliary metadata; parameters that directly affect business results should usually be passed explicitly to functions. Do not store passwords, raw tokens, or unnecessary sensitive data in context; avoid logging the `Authentication` object directly.

**Mistake 1 – reading on the wrong side of `contextWrite`:** placing the reader downstream yields the default value or a missing-key error. Fix by identifying exactly which subscriber needs the key, then placing `contextWrite` appropriately downstream.

**Mistake 2 – calling `Context.of` without attaching it to the pipeline:** creating an isolated `Context` does not affect a subscription; apply `contextWrite` at the integration point.

**Mistake 3 – using `ThreadLocal` as a global request variable:** bugs appear when switching schedulers or reusing event-loop threads. Fix using `Context`, reactive APIs, or a controlled context-propagation bridge.

**Mistake 4 – nesting `subscribe()`/`block()` inside a service:** creates a separate subscription and skews context scope while breaking backpressure/error propagation. Fix by returning and composing publishers.

**Mistake 5 – using `get(key)` for optional keys:** a missing key can raise an error. Use `getOrDefault`/`hasKey` or supply required context at the request boundary.

**Mistake 6 – thinking immutability means all values are immutable:** `Context` does not mutate the old map, but it can hold a mutable object referenced by multiple operators. Prefer small, immutable values; do not store shared mutable state to track requests.

**Mistake 7 – injecting fake security context in production:** `withAuthentication` only attaches a context value; it does not replace authentication, authorization, or session/token management. Use the filter chain and Spring Security configuration for real authentication; use direct injection only in tests or explicitly designed, tightly controlled flows.

## 10. Testing and Self-Assessment Questions

In a project with the `io.projectreactor:reactor-test` test dependency matching your Reactor Core version, you can test a subscription directly:

~~~java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

StepVerifier.create(
    Mono.deferContextual(view ->
        Mono.just(view.<String>get("traceId")))
    .contextWrite(Context.of("traceId", "req-9"))
)
.expectNext("req-9")
.verifyComplete();
~~~

Cases to include in a test suite: required key present/missing; `contextWrite` in wrong/right position; two subscriptions on the same publisher with different contexts; scheduler switch; inner `flatMap`; security context with/without authentication along the request flow. Avoid relying on thread names or timing to prove context correctness.

Answer these three questions yourself:
1. If `Mono.deferContextual(...)` appears after `contextWrite` in the chain, will it always see the written value? **No**; you must check upstream/downstream placement.
2. Do two WebFlux requests running sequentially on the same event-loop thread necessarily share the same Reactor Context? **No**; context is bound to each subscription's subscriber.
3. When calling `ReactiveSecurityContextHolder.clearContext()`, is the client-side token revoked? **No**; that only operates on the context entry within the reactive scope under consideration.

## Official Documentation

- Project Reactor — Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Project Reactor — Context-Propagation Support: https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html
- Spring Security — `ReactiveSecurityContextHolder` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
