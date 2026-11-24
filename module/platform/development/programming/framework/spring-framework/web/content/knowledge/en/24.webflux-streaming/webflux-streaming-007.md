# Propagating Context via Reactor Context Instead of ThreadLocal Assumptions in Streaming WebFlux

## 1. Problem: One Request Crosses Multiple Threads While Preserving Its Context

In synchronous Spring MVC, a single request may run continuously on one Servlet worker thread. Legacy code therefore often stores a correlation ID, current user, locale, or MDC in `ThreadLocal` and reads it across methods on that same thread. **Spring WebFlux makes no promise that a request runs on a single Java thread.** Reactor Netty HTTP callbacks, `publishOn`, `subscribeOn`, `flatMap` with async sources, `Mono.delay`, WebClient, and reactive data drivers can continue execution on different execution contexts.

Real-world scenario:

```text
Client GET /api/events X-Request-Id: req-A
    │
    ▼
reactor-http-nio-2           receives HTTP, builds Mono/Flux chain
    │
    ├── WebClient sends non-blocking remote request
    └── Mono.delay(...)      awaits timer without holding a worker thread
                 │
                 ▼
parallel-1                  data arrives, pipeline continues
                 │
                 ├── read ThreadLocal: not guaranteed to see req-A
                 └── read Reactor Context: sees req-A if the entire
                      chain has contextWrite in the right position
                 │
                 ▼
reactor-http-nio-3          writes more HTTP/SSE body
```

Thread names are illustrative only. Never design functionality around event-loop thread names or counts. With **Reactor Context**, request metadata travels with the signal chain through the **subscription**, independent of any specific thread. This matters especially in **Streaming WebFlux**, where a Flux can stay open a long time, cross schedulers, trigger many callbacks, and be cancelled by clients.

### 1.1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish `ThreadLocal` bound to a Java thread from `Context` bound to each **Reactor Subscriber/subscription**.
2. Use `contextWrite`, `Mono.deferContextual`, `Flux.deferContextual`, `Context`, and `ContextView` in the proper propagation direction.
3. Explain why `contextWrite` at the bottom of source code executes **before upstream emits onNext**, and why reordering operators changes the observed value.
4. Control context override scopes across `flatMap`, `concatMap`, and nested publishers to prevent cross-request/tenant context leaks.
5. Put a correlation ID from a WebFlux `WebFilter` into Reactor Context and read it in a service, even after `Mono.delay` and `subscribeOn`.
6. Understand reading Reactor Context in SSE/Flux: context needed per event, on cancellation, and on error paths.
7. Distinguish native Reactor Context from Micrometer Context Propagation/MDC/ThreadLocal bridges in default and automatic modes.
8. Never treat a client-supplied header as authentication, and never put secrets in logs or shared contexts.
9. Build a runnable Spring Boot 3/Java 17 project with WebFilter, service, controller, WebTestClient, and StepVerifier tests.
10. Debug "context missing", mixed request IDs, callbacks running outside the chain, and missing reactive security principals.

**Scope:** Spring Framework 6.x, Project Reactor 3.6.x / Spring Boot 3.3.x, Java 17+. This lesson does not claim all `ThreadLocal` usage disappears in WebFlux: configurable automatic restoration mechanisms exist, yet they **do not change the core principle** that a reactive pipeline does not own a fixed thread.

## 2. The Right Mental Model for ThreadLocal vs. Context

### 2.1. ThreadLocal: State Lives in the Currently Executing Thread

Imperative example:

```java
private static final ThreadLocal<String> REQUEST_ID =
        new ThreadLocal<>();

static void handleRequest() {
    REQUEST_ID.set("req-123");
    try {
        callBusinessFunction(); // if same thread, get() sees req-123
    } finally {
        REQUEST_ID.remove(); // critical for thread pools
    }
}
```

`ThreadLocal.get()` accesses state of the **current Java Thread**. It does not follow a logical request when work moves to another executor/scheduler. With reused thread pools, forgetting `remove()` can even leak stale data into another request.

In synchronous MVC, set→get→remove makes sense when code and framework clearly manage scope. In WebFlux, even if a callback happens to run "on the same thread" by coincidence, that is **not a contract** business code may rely on.

### 2.2. Reactor Context: State Lives with the Subscriber

`reactor.util.context.Context` is an **immutable** key-value container (each mutation returns a new `Context`) attached to a subscription. Upstream operators access context supplied by the downstream `Subscriber`.

Characteristics:

- Keys/values cannot be `null`; context is not a shared mutable `Map`.
- Each `put`/`delete` creates a new logical context instance.
- Keys can be Strings, class/object keys, or dedicated key objects; namespace keys to avoid collisions.
- `ContextView` provides read-only access: `get`, `getOrDefault`, `hasKey`, `stream`.
- `Context` provides copy-on-write operations: `put`, `delete`, `putAll`.
- Accessible at **subscription time / inside the reactive chain**, not in arbitrary synchronous code running outside the reactive chain.
- Not guaranteed to propagate into arbitrary `ExecutorService`, `CompletableFuture`, external callbacks, or third-party libraries merely because an outer method returns a `Mono`.

**Differences in where state attaches:**

| Topic | ThreadLocal | Reactor Context |
| --- | --- | --- |
| Belongs to | Currently executing Java Thread | Subscriber/subscription |
| Cross-thread | Does not follow automatically | Accessible across Reactor operators when context propagates |
| Lifecycle | Thread and explicit cleanup | Subscription/reactive chain |
| Mutability | `ThreadLocal.set` mutates value | Immutable Context returning a new instance |
| Isolation between requests | Depends on set/remove and thread reuse | Scoped per subscription/context boundary |
| How to read | `THREAD_LOCAL.get()` | `Mono.deferContextual(ctx -> ...)` |
| How to write | `THREAD_LOCAL.set(x)` | `publisher.contextWrite(ctx -> ctx.put(key,x))` |
| Usable in non-Reactor callbacks | Directly if on same thread | Requires bridge/`ContextSnapshot`/explicit arguments |
| Risks | Leaks, stale values, lost propagation | Wrong operator order, context lost outside chain, key collisions |

Never treat Reactor Context as a "global map" accessible from any random function. It is **subscriber-oriented context**, read properly via Reactor APIs.

### 2.3. Distinguishing Three Objects

- `Context`: *semantically immutable* read/write interface; `put` methods return a new instance.
- `ContextView`: **read-only** interface; the type `deferContextual` passes to the lambda.
- Micrometer's `ContextSnapshot`: **distinct** from Reactor Context; captures/restores context mechanisms like `ThreadLocal` from/to registered accessors.

Example:

```java
Context original = Context.of("traceId", "A");
Context updated = original.put("tenantHint", "tenant-1");

System.out.println(original.hasKey("tenantHint")); // false
System.out.println(updated.hasKey("tenantHint"));  // true
```

This snippet requires importing `reactor.util.context.Context`; in a Java project with Reactor, stdout is `false` and `true`. Note `tenantHint` is illustrative data only—**never** treat a client-supplied tenant ID as authorization proof.

## 3. Writing Context: contextWrite

`contextWrite` is the standard API to enrich context for **upstream** operators.

```java
Mono<String> pipeline =
    Mono.deferContextual(ctx ->
        Mono.just("trace=" + ctx.get("traceId")))
        .contextWrite(Context.of("traceId", "req-A"));
```

When `pipeline` is subscribed, the result is:

```text
trace=req-A
```

`contextWrite(ContextView)` merges the new context with downstream context; `contextWrite(Function<Context,Context>)` builds context with merge/replace logic.

```java
Mono<String> result =
    Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("traceId", "absent")))
      .contextWrite(ctx -> ctx.put("traceId", "req-A"));
```

Keep context values small, immutable, or thread-safe. Never stuff whole HTTP request bodies, large lists, `EntityManager`s, mutable Servlet requests, unbounded buffers, or unnecessary tokens/secrets into Context.

### 3.1. Why Does contextWrite at the Bottom of Code Affect Operators Above?

Pipelines are read top-to-bottom in **assembly order**, yet subscription flows in the opposite direction:

```text
Source / Mono.deferContextual          ── produces value
       ↑ context seen from downstream
.map(...)                               ── processes item
       ↑
.contextWrite(key=value)                ── writes context for upstream
       ↑ subscription flows bottom-up
Subscriber / WebFlux HTTP writer
```

Thus:

```java
Mono.deferContextual(ctx -> Mono.just(ctx.get("k")))
    .contextWrite(Context.of("k", "v"));
```

reads `v`. Moving `contextWrite` **above** a `flatMap` that reads context below it prevents that `flatMap` from seeing the value.

### 3.2. Example of Wrong Operator Placement

```java
Mono<String> wrong = Mono.just("value")
    .contextWrite(ctx -> ctx.put("k", "inside"))
    .flatMap(x -> Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("k", "missing"))));
```

Expected result: **missing**. Because `flatMap` sits downstream of `contextWrite`; that context write affects only upstream.

Fix:

```java
Mono<String> right = Mono.just("value")
    .flatMap(x -> Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("k", "missing"))))
    .contextWrite(ctx -> ctx.put("k", "inside"));
```

Result: **inside**. Both snippets can go into a Java method with Reactor imports, verified via `StepVerifier` (Section 14).

### 3.3. Overriding the Same Key: Position Decides the Value

```java
Mono<String> result =
    Mono.deferContextual(ctx ->
        Mono.just(ctx.get("language")))
       .contextWrite(ctx -> ctx.put("language", "vi"))
       .contextWrite(ctx -> ctx.put("language", "en"));
```

Result: **vi**. Two operators write the same key; for the source, `contextWrite(vi)` is closer to the source and overrides `en`. The value `en` can still be seen by operators in between/downstream depending on scope.

Never build security by "overriding role/tenant" inside an unchecked inner publisher. Context is not an auth barrier; authoritative user/tenant identity must come from Spring Security/trusted context.

### 3.4. Only One Subscriber Sees a Specific Context View

A cold publisher can be subscribed multiple times with distinct contexts:

```java
Mono<String> source =
    Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("requestId", "missing")));

Mono<String> a =
    source.contextWrite(Context.of("requestId", "req-A"));
Mono<String> b =
    source.contextWrite(Context.of("requestId", "req-B"));
```

`a` yields `req-A`, `b` yields `req-B`. No need to store `requestId` in a static field or mutate a shared Context.

## 4. Reading Context Properly: deferContextual and ContextView

`Mono.deferContextual` builds an inner Mono using the current subscription's `ContextView`. `Flux.deferContextual` works identically for Flux.

```java
Mono<String> currentRequestId() {
    return Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("requestId", "anonymous")));
}
```

Never write `Mono.just(Context.of(...).get(...))` expecting the current context; you just created a brand-new map unrelated to the subscriber. Nor is there a universal static `ReactorContext.current()` usable anywhere like `ThreadLocal.get()`.

### 4.1. Reading Inside an Asynchronous Operator

```java
Mono<String> result =
    Mono.delay(Duration.ofMillis(10))
        .flatMap(tick ->
            Mono.deferContextual(ctx ->
                Mono.just("trace=" +
                    ctx.getOrDefault("traceId", "none"))))
        .contextWrite(Context.of("traceId", "req-42"));
```

After the timer fires, the inner `Mono.deferContextual` still sees the subscription's context. Result is `trace=req-42`. Never test using thread names like "parallel-1", since scheduler pool sizes/names vary.

### 4.2. When to Use get, getOrDefault, hasKey?

- `ctx.get(key)`: requires the key to exist; otherwise throws `NoSuchElementException`.
- `ctx.getOrDefault(key, fallback)`: fits optional metadata like correlation IDs.
- `ctx.hasKey(key)`: checks presence.
- `ctx.getOrEmpty(key)`: reads an `Optional` value when suited to the API.
- `ctx.stream()`: only for tightly controlled diagnostics; never dump the whole context to logs as it may contain auth/tracing values.

For mandatory security principals, **never fall back to "admin"** when a key is missing. A missing context indicates an authorization failure or propagation bug; fail closed.

### 4.3. String or Object Keys?

```java
public final class Keys {
    public static final String TRACE_ID = "example.trace-id";
    private Keys() {}
}
```

Namespaced strings avoid collisions across libraries. For stronger type safety and collision resistance, you can use `private static final Object TRACE_KEY = new Object()` as the key, provided **the exact same key object** is shared between writers and readers.

**Never** allocate `new Object()` on each read/write, as key identities will not match. The demo project below uses a string constant for easy observation/testing.

## 5. Benefits in Streaming WebFlux: Many onNext Signals, One Context

An SSE `Flux` may emit three events or stay alive for minutes. Context attaches to the client's subscription, so every event can read the same correlation ID.

```java
Flux<String> events =
    Flux.interval(Duration.ofMillis(100))
        .take(3)
        .concatMap(n ->
            Mono.deferContextual(ctx ->
                Mono.just(ctx.get("traceId") + ":" + n)))
        .contextWrite(Context.of("traceId", "stream-A"));
```

On normal completion, emitted items are:

```text
stream-A:0
stream-A:1
stream-A:2
```

Because `Flux.interval` ticks on another scheduler, `ThreadLocal.get()` is not guaranteed to match the HTTP request start thread. Yet `deferContextual` in the composed inner publisher sees the subscriber's context.

### 5.1. One Client Must Never Read Another Client's Request ID

Suppose A sends `X-Request-Id: A` and B sends `X-Request-Id: B`. Using a static mutable field:

```java
// ANTI-PATTERN — requests A/B can overwrite each other.
static String currentRequestId;
```

causes A's events to show B. With Reactor Context, the filter sets the key **per subscriber**; even as signals interleave, contexts remain isolated by subscription.

**However:** a hot/shared publisher may require explicit scope design. If you build a `Flux.share()` in a singleton service using the first request's context, do not assume later subscribers' contexts automatically apply properly to the shared upstream. When each user needs their own trace/tenant, read context in each subscriber's **own downstream branch** or pass immutable metadata explicitly after authentication; never share an upstream holding user-specific context without understanding multicast/replay semantics.

### 5.2. SSE and Cancellation

Client SSE disconnects can trigger subscription **cancel**. `doFinally` receives `SignalType.CANCEL` and fits cleanup/metrics; `doOnComplete` does not run on cancel.

```java
Flux<String> stream = service.events()
    .doFinally(signalType -> {
        // COMPLETE, ERROR, or CANCEL.
        // Do not block event loop; avoid logging sensitive context.
    });
```

This is a snippet with an assumed `service`, not a standalone runnable file. If you need the request ID inside `doFinally`, capture the **immutable request ID already read via `deferContextual`** and build the inner chain around cleanup. Never expect an arbitrary callback to directly access current context on its own.

### 5.3. Response Already Started and Subsequent Errors

An SSE response that has committed status 200 and emitted events cannot reliably switch to HTTP 500 if upstream fails mid-stream. Use a protocol-level error event or stream-close/retry policy. Context propagation aids tracing/diagnostics; it **does not alter** HTTP semantics.

### 5.4. Backpressure Does Not Depend on ThreadLocal

Reactive Streams demand/cancellation belong to the subscription. Reactor Context carries metadata along the subscription, yet it **does not speed up downstream**, does not bound `onBackpressureBuffer` memory, and does not force remote producers to obey demand. Design buffering/batching/rate limits separately.

## 6. Context Across flatMap, concatMap, publishOn, and subscribeOn

### 6.1. Scheduler Boundary

```java
Mono<String> pipeline = Mono.just("start")
    .publishOn(Schedulers.parallel())
    .flatMap(value ->
        Mono.deferContextual(ctx ->
            Mono.just(value + "-" + ctx.get("traceId"))))
    .contextWrite(Context.of("traceId", "req-123"));
```

Result: `start-req-123`. `publishOn` shifts where downstream signals run, while Reactor Context rides with the subscriber along the chain.

### 6.2. Inner Publisher Scoped Context

```java
Mono<String> result = Mono.just("hello")
    .flatMap(word ->
        Mono.deferContextual(ctx ->
            Mono.just(word + "-" + ctx.get("k")))
        .contextWrite(Context.of("k", "inner")))
    .flatMap(value ->
        Mono.deferContextual(ctx ->
            Mono.just(value + "-" + ctx.get("k"))))
    .contextWrite(Context.of("k", "outer"));
```

Result: `hello-inner-outer`. Context `inner` applies to the first `flatMap`'s inner publisher without overwriting the downstream main sequence. Verify complex chains with `StepVerifier` before relying on scopes for audit/security.

### 6.3. Do Not Write Context and Expect a Sibling Branch to Read It

Two independent inner publishers under `flatMap` can have distinct local context overrides. A `contextWrite` on branch A does not modify branch B's context. To share metadata cleanly, place context downstream of both or pass an immutable value as an argument.

### 6.4. concatMap vs. flatMap

`flatMap` can interleave signals when inner publishers are async; `concatMap` serializes inner streams in order. **Both preserve Reactor Context** when composed properly. Pick operators based on ordering/concurrency needs—do not choose `concatMap` just to "fix" `ThreadLocal` propagation.

### 6.5. publishOn Does Not Turn Blocking Sources Non-Blocking

```java
Mono<String> bad =
    Mono.just(legacyJdbc.read()) // blocking runs immediately!
        .publishOn(Schedulers.boundedElastic());
```

`legacyJdbc.read()` runs **before the Mono is even created**. When forced to bridge legacy blocking code:

```java
Mono<String> bridged =
    Mono.fromCallable(() -> legacyJdbc.read())
        .subscribeOn(Schedulers.boundedElastic());
```

These are snippets with an assumed dependency. `boundedElastic` does not make JDBC a reactive DB driver; blocking sources still need timeouts and pool/concurrency limits. Context remains readable via `deferContextual` afterward, yet `ThreadLocal` inside JDBC/custom loggers does not automatically get request metadata unless bridged properly.

## 7. What Reactor Context Does NOT Do Automatically

1. **Does not create authentication**: putting a request ID/tenant header in context does not make it a trusted principal.
2. **Does not preserve arbitrary framework ThreadLocals**: requires context-propagation integration/registered accessors if `ThreadLocal` is still used.
3. **Does not propagate into arbitrary ExecutorService**: leaving a Publisher chain requires passing immutable values or `ContextSnapshot`/context-aware wrappers.
4. **Does not create distributed tracing**: internal trace IDs do not automatically travel over HTTP headers to remote services; use W3C Trace Context instrumentation when needed.
5. **Does not manage HttpSession**: Context is subscription-scoped, not a persistent session store.
6. **Is not a cache**: `Context.put` does not cache or share data across requests.
7. **Does not automatically clean up side effects**: cancellation-aware lifecycles and Reactor resource management are required.
8. **Does not add backpressure** to callback sources lacking demand support.
9. **Does not replace security context**: Spring Security reactive APIs have their own conventions.
10. **Does not guarantee data visibility outside Reactor operators**: plain callbacks/thread pools have independent lifecycles.

### 7.1. The "Manual subscribe()" Trap in Handlers

```java
Mono<Void> writeAudit() {
    return Mono.deferContextual(ctx -> auditService.save(
        ctx.get("requestId")));
}

Mono<Response> badHandler() {
    writeAudit().subscribe(); // detaches subscription from HTTP chain
    return service.load().map(this::toResponse);
}
```

This is illustrative pseudocode, not a standalone class. The detached subscription from `subscribe()` can get an **empty Context**, handle errors outside HTTP, and cause side effects uncancelled by the request. The right pattern composes auditing into the returned publisher:

```java
Mono<Response> goodHandler() {
    return writeAudit()
        .then(service.load())
        .map(this::toResponse);
}
```

In real apps, durable/exactly-once auditing needs transactions/outboxes/event logs, not merely `then`. The point here is **keeping one composed subscription**, avoiding manual `subscribe()`.

### 7.2. Completeness: Errors and Empty

If `Mono.deferContextual(ctx -> Mono.just(ctx.get("key")))` lacks the key, the chain signals an error. For optional metadata, use `getOrDefault` explicitly. Never use `onErrorResume(any -> Mono.empty())` to swallow DB errors or missing security context; it can turn failures into empty 200/404 responses depending on the web layer.

## 8. ThreadLocal with Logging MDC: Don't Assume, Yet You Don't Always Rewrite Everything

Logback/SLF4J MDC commonly uses `ThreadLocal`. Synchronous code:

```java
MDC.put("requestId", "req-1");
log.info("processing...");
MDC.remove("requestId");
```

works on the same thread when cleaned up properly. However, if a `Mono` runs partly on `reactor-http-nio` and partly on `parallel`, MDC does not automatically follow the request in Reactor without a bridge. Even if log messages occasionally show the correlation ID in some callbacks, **never conclude it always works**.

### 8.1. A Controlled Manual Approach

For a short synchronous logging block, read `ContextView` and set/restore MDC strictly around the callback:

```java
Mono<Void> logWithContext() {
    return Mono.deferContextual(ctx -> {
        String requestId =
            ctx.getOrDefault("requestId", "missing");

        String previous = MDC.get("requestId");
        try {
            MDC.put("requestId", requestId);
            log.info("Processing with trace context");
        } finally {
            if (previous == null) MDC.remove("requestId");
            else MDC.put("requestId", previous);
        }
        return Mono.empty();
    });
}
```

This illustrative snippet needs logger and MDC imports; it is not standalone-runnable. The set/restore scope **wraps only the synchronous log call**; never set MDC, return an async `Mono`, and expect `ThreadLocal` to survive the whole subscription. Across many log sites, use framework-integrated Micrometer tracing/observability instead of manual boilerplate.

### 8.2. Context Propagation Bridge: Two Modes

Since Reactor 3.5, Reactor Core supports integrating the `io.micrometer:context-propagation` SPI:

- **Default/limited mode**: only certain operators like `handle`/`tap` restore registered `ThreadLocal` state within specific scopes. There is no promise that every `map`/`flatMap` callback sees MDC.
- **Automatic mode**: when `Hooks.enableAutomaticContextPropagation()` is enabled, Reactor attempts to restore registered `ThreadLocal`s via `ThreadLocalAccessor` across many operator callbacks. Enable it at startup because it applies to **new subscriptions**.
- `contextCapture()`: snapshots **registered** `ThreadLocal` values at subscription time and writes them into Reactor Context so upstream can see them.
- `contextWrite(...)`: writes key/value pairs directly into Reactor Context; it does not imply `ThreadLocal` restoration by itself.
- Automatic mode incurs overhead and has cleanup semantics; an absent key can signal clearing the `ThreadLocal` to prevent leaks.

**Crucial condition:** enabling the hook alone **is not enough** to propagate an arbitrary `new ThreadLocal<>()`. You need the `context-propagation` dependency and a `ThreadLocalAccessor` registered by a library or application code.

### 8.3. Spring Boot Property on Supported Versions

In Spring Boot 3.3, you can configure:

```properties
spring.reactor.context-propagation=auto
```

This property activates Reactor's automatic context propagation; it does not remove the need for registered accessors or turn Reactor Context into implicit user identity. Avoid mixing manual hook calls in multiple places with the property without reason. Benchmark and verify context lifecycles for production.

If the application only needs a request correlation ID in business/service code, **reading Context directly** via `deferContextual` is usually clearer than relying on `ThreadLocal` restoration. When OpenTelemetry/Micrometer/SLF4J compatibility is needed, use standard integrations and verify log traces in tests.

### 8.4. Comparison Table of Expected Outcomes

| Condition | Reactor Context `deferContextual` | Arbitrary `ThreadLocal.get()` |
| --- | --- | --- |
| Normal Reactor pipeline with `contextWrite` | Reads valid key | Not guaranteed |
| Thread switch via `publishOn` | Still reads context across operators | Not guaranteed |
| Default Micrometer context propagation | Still reads context | Restored in supported operators for registered accessors |
| Automatic propagation with registered accessor | Still reads context | May restore per contract/library |
| Automatic mode with unregistered `ThreadLocal` | Still reads context | Not guaranteed |
| Work detached via manual `subscribe` | May lose parent context | Not guaranteed |
| Offloaded to raw `ExecutorService` | Needs explicit propagation | Needs explicit propagation |
| Hot source shared across multiple subscribers | Requires per-subscriber scope design | Risk of cross-talk if misplaced |

## 9. Spring Security: Where Does SecurityContext Live in WebFlux?

Reactive Spring Security uses reactive contexts and `SecurityWebFilterChain`, not a Servlet `SecurityContextHolder` `ThreadLocal` present on every scheduler. Spring Security provides `ReactiveSecurityContextHolder`:

```java
Mono<String> currentUser() {
    return ReactiveSecurityContextHolder.getContext()
        .map(security -> security.getAuthentication())
        .filter(auth -> auth != null && auth.isAuthenticated())
        .map(auth -> auth.getName());
}
```

This snippet requires `spring-boot-starter-security`, imports, and proper authentication config. **Never** build a `SecurityContext` from an `X-User-Role` request header and put it into Reactor Context as a "login" shortcut.

### 9.1. Request ID Context Differs from Authorization Context

- Client `X-Request-Id`: usable for log correlation, **never** authenticates identity.
- Tracing context: may come from W3C `traceparent` governed by ingress/tracing policies.
- Principal: created by Spring Security via trusted authentication methods.
- Tenant ID: must be derived from principal/session/authorization, optionally cross-checked against route parameters or validated headers per policy.
- Locale/feature flags: valid metadata, though needing trusted sources if affecting sensitive behavior.

Never log tokens/credentials, and never stash mutable principal objects in a singleton `Map` assuming it is safe context across requests.

## 10. WebClient, R2DBC, and Subscription Boundaries

### 10.1. Composing WebClient in the Same Chain

```java
Mono<String> result = Mono.deferContextual(ctx -> {
    String correlation = ctx.get("requestId");

    return webClient.get()
        .uri("/remote/items")
        .header("X-Request-Id", correlation)
        .retrieve()
        .bodyToMono(String.class);
});
```

This snippet assumes an injected `WebClient` and hypothetical remote URL; it is not a complete class. Here Reactor Context **is read explicitly**, then the ID is placed into an outbound HTTP header. Reactor Context **does not automatically cross the network** without client instrumentation or explicit application logic.

**Never forward security credentials** pulled from context as arbitrary outbound headers; use OAuth/OIDC, token exchange, or policy-governed trust delegation.

### 10.2. R2DBC Reactive Repository

```java
Mono<Note> selected =
    repository.findById(id)
       .flatMap(note ->
           Mono.deferContextual(ctx -> {
               audit.record(ctx.get("requestId"), note.id());
               return Mono.just(note);
           }));
```

Illustrative snippet: if `audit.record` is blocking, replace it with a reactive publisher/bridge; calling sync code and returning `Mono` still blocks the caller thread. Staying inside Reactor composition preserves context; `block()` or manual `subscribe()` breaks those semantics.

### 10.3. Transaction Context Differs from Request ID

Reactive transaction management uses subscriber Context to carry transaction resources across operators instead of imperative `@Transactional` `ThreadLocal`s. However, manually putting a `transactionId` key into Reactor Context **does not create a real transaction**. Use `TransactionalOperator`/Spring reactive transaction infrastructure with a supported driver. Avoid sharing one transaction-scoped publisher across independent subscribers.

### 10.4. Returning to a Legacy ExecutorService

If forced to use a non-Reactor async API, pass an immutable subset (e.g., request ID) as a method parameter, or use Micrometer `ContextSnapshot`/context-aware Executor wrappers configured with proper accessors. Never stash a whole `ContextView` in a global static variable or keep it alive longer than the request needs.

## 11. Runnable Demo: Spring Boot 3.3.13, Java 17, WebFlux Context

This is a complete application needing no database or remote service. All code uses `spring-boot-starter-webflux` and `reactor-core` managed by Spring Boot. The demo uses Reactor Context directly **without enabling automatic ThreadLocal propagation** because the goal is to demonstrate independence from `ThreadLocal`.

APIs:

- `GET /api/context`: returns `requestId` and `stage = direct`.
- `GET /api/context/delayed`: crosses `Mono.delay`, still reads `requestId`.
- `GET /api/context/bounded`: hops briefly onto `Schedulers.boundedElastic()`, preserves `requestId`.
- `GET /api/context/scoped`: overrides context in a local branch to `local-override` to illustrate scoping; the filter's response header keeps the outer ID.
- `GET /api/context/events`: 3 SSE events, each reading context on an inner Mono.
- `GET /api/context/error`: reactive 400 error; `WebFilter` already set the correlation response header.
- `GET /api/context/missing`: unmapped route confirming WebFlux 404.

Sample header `X-Request-Id` is solely for **diagnostics**, never for auth/tenant identity. The filter accepts only allowlisted characters up to length ≤64 to curb log injection; invalid input gets a fresh UUID.

### 11.1. File Structure

```text
reactor-context-demo/
├── pom.xml
└── src/
    ├── main/java/example/
    │   ├── ReactorContextApplication.java
    │   ├── ContextKeys.java
    │   ├── TraceReply.java
    │   ├── RequestIdFilter.java
    │   ├── TraceService.java
    │   └── TraceController.java
    └── test/java/example/
        ├── ContextOperatorsTest.java
        └── TraceHttpTest.java
```

### 11.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-context-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**Note:** Do not add `spring-boot-starter-web` to the demo, because when both MVC and WebFlux starters are present Boot normally picks Servlet MVC. `WebFilter` here belongs to `org.springframework.web.server` and targets the reactive web application type.

### 11.3. ReactorContextApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactorContextApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactorContextApplication.class, args);
    }
}
```

### 11.4. ContextKeys.java

```java
package example;

public final class ContextKeys {

    public static final String REQUEST_ID = "example.request-id";

    private ContextKeys() {
    }
}
```

Share a single constant key between filter and service instead of copy-pasting string literals across files.

### 11.5. TraceReply.java

```java
package example;

public record TraceReply(
        String requestId,
        String stage,
        String threadName) {
}
```

`threadName` is strictly for diagnostic observation; never write assertions like "must be thread X" because Reactor schedulers and Netty thread names vary by environment/version.

### 11.6. RequestIdFilter.java

```java
package example;

import java.util.UUID;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(0)
public class RequestIdFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String requested = exchange.getRequest()
                .getHeaders().getFirst("X-Request-Id");

        final String requestId = requested != null &&
                requested.matches("[A-Za-z0-9._-]{1,64}")
            ? requested
            : UUID.randomUUID().toString();

        exchange.getResponse().getHeaders()
                .set("X-Request-Id", requestId);

        return chain.filter(exchange)
            .contextWrite(context ->
                context.put(ContextKeys.REQUEST_ID, requestId));
    }
}
```

Explanation:

1. `WebFilter` runs in the reactive `WebHandler` chain.
2. Reads the optional ID from the HTTP request and validates characters/length.
3. Sets a response header so clients can correlate errors with requests.
4. Returns `chain.filter(exchange).contextWrite(...)` without calling `block()` or `subscribe()`.
5. Everything **upstream** of `contextWrite` can read the ID via `deferContextual`, even across scheduler hops.

Client-supplied IDs remain **untrusted for authorization** and must never determine principal/tenant. Production tracing instrumentation can generate/validate trace IDs independently.

### 11.7. TraceService.java

```java
package example;

import java.time.Duration;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class TraceService {

    public Mono<TraceReply> snapshot(String stage) {
        return Mono.deferContextual(context -> {
            String requestId = context.getOrDefault(
                    ContextKeys.REQUEST_ID, "missing");

            return Mono.just(new TraceReply(
                requestId,
                stage,
                Thread.currentThread().getName()));
        });
    }

    public Mono<TraceReply> delayed() {
        return Mono.delay(Duration.ofMillis(10))
                .flatMap(value -> snapshot("after-delay"));
    }

    public Mono<TraceReply> bounded() {
        return Mono.fromCallable(() -> "legacy-stage")
                .subscribeOn(Schedulers.boundedElastic())
                .flatMap(this::snapshot);
    }

    public Mono<TraceReply> scoped() {
        return snapshot("local-scope")
            .contextWrite(context ->
                context.put(
                    ContextKeys.REQUEST_ID, "local-override"));
    }
}
```

- `snapshot` reads `requestId` when the **subscription** reaches `deferContextual`. No static state is used.
- `delayed` runs through the timer scheduler then `flatMap`s into `snapshot`; context remains intact.
- `bounded` shows context stays accessible after `subscribeOn(boundedElastic)`. The callable returns a small `String` and **performs no real blocking I/O**.
- `scoped` intentionally overrides the same key closer to the source; the response body sees `local-override`, while the WebFilter response header reflects the original ID because it was set from the request before body subscription.

Never cite matching `threadName` values across two requests as proof of context isolation, since scheduler names repeat. Tests assert the *requestId value*.

### 11.8. TraceController.java

```java
package example;

import java.time.Duration;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class TraceController {

    private final TraceService service;

    public TraceController(TraceService service) {
        this.service = service;
    }

    @GetMapping("/api/context")
    public Mono<TraceReply> direct() {
        return service.snapshot("direct");
    }

    @GetMapping("/api/context/delayed")
    public Mono<TraceReply> delayed() {
        return service.delayed();
    }

    @GetMapping("/api/context/bounded")
    public Mono<TraceReply> bounded() {
        return service.bounded();
    }

    @GetMapping("/api/context/scoped")
    public Mono<TraceReply> scoped() {
        return service.scoped();
    }

    @GetMapping(
        value = "/api/context/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<TraceReply>> events() {
        return Flux.interval(Duration.ofMillis(10))
            .take(3)
            .concatMap(index ->
                service.snapshot("event-" + index)
                    .map(reply ->
                        ServerSentEvent.<TraceReply>builder()
                            .id(Long.toString(index))
                            .event("trace")
                            .data(reply)
                            .build()));
    }

    @GetMapping("/api/context/error")
    public Mono<TraceReply> error() {
        return Mono.error(new ResponseStatusException(
            HttpStatus.BAD_REQUEST,
            "demonstration error"));
    }
}
```

**Streaming chain:** each `index` from the Flux timer maps to a `service.snapshot(...)`. Because the inner Mono belongs to the same composed subscription, the WebFilter's context appears in every SSE payload. `take(3)` caps the stream so tests don't hang. Infinite production SSE needs heartbeats, request cancellation, resource limits, and proxy timeouts.

**Error path:** `ResponseStatusException(HttpStatus.BAD_REQUEST)` is handled by WebFlux exception infrastructure as 400 before commit. The filter already set the `X-Request-Id` header, helping clients correlate errors even when the framework generates the error body.

### 11.9. Running Maven/cURL

From the directory containing `pom.xml` (JDK 17+, Maven):

```bash
mvn test
mvn spring-boot:run
```

**Note:** These commands are instructions for learners. This document is self-contained code; it makes no claim that tests were executed in the authoring environment.

Direct call:

```bash
curl -i -H "X-Request-Id: demo-A" \
  http://localhost:8080/api/context
```

HTTP 200, header `X-Request-Id: demo-A`, and JSON body like:

```json
{
  "requestId": "demo-A",
  "stage": "direct",
  "threadName": "reactor-http-nio-1"
}
```

**Do not** rely on the `threadName` value above as it is only an example; real names vary. Only `requestId` and `stage` are stable contract fields.

Delayed step:

```bash
curl -i -H "X-Request-Id: demo-B" \
  http://localhost:8080/api/context/delayed
```

Expected body contains:

```json
{"requestId":"demo-B","stage":"after-delay"}
```

`threadName` varies by runtime.

`boundedElastic` step:

```bash
curl -i -H "X-Request-Id: demo-C" \
  http://localhost:8080/api/context/bounded
```

Expected `requestId` `demo-C` and `stage` `legacy-stage`.

Scope:

```bash
curl -i -H "X-Request-Id: outer-123" \
  http://localhost:8080/api/context/scoped
```

Expected **header** `X-Request-Id: outer-123`, while **body** has `"requestId":"local-override"`. This demo intentionally overrides to illustrate scope; never override correlation IDs in production business code without explicit reason and audit.

Invalid header:

```bash
curl -i -H "X-Request-Id: invalid id" \
  http://localhost:8080/api/context
```

Expected header/body `requestId` is a newly generated UUID per validation logic; never assert a fixed UUID.

SSE:

```bash
curl -N -i -H "X-Request-Id: stream-9" \
  -H "Accept: text/event-stream" \
  http://localhost:8080/api/context/events
```

The SSE body contains three events (formatting/whitespace and thread names are not fixed):

```text
id:0
event:trace
data:{"requestId":"stream-9","stage":"event-0","threadName":"..."}

id:1
event:trace
data:{"requestId":"stream-9","stage":"event-1","threadName":"..."}

id:2
event:trace
data:{"requestId":"stream-9","stage":"event-2","threadName":"..."}

```

Do not expect SSE chunk boundaries to align with TCP packet boundaries. `curl -N` only disables curl's output buffering.

## 12. Tests: WebTestClient Verifying Context Over Real HTTP

File `src/test/java/example/TraceHttpTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class TraceHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void requestIdAppearsInBodyAndResponseHeader() {
        client.get().uri("/api/context")
            .header("X-Request-Id", "req-one")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("X-Request-Id", "req-one")
            .expectBody()
                .jsonPath("$.requestId").isEqualTo("req-one")
                .jsonPath("$.stage").isEqualTo("direct");
    }

    @Test
    void contextSurvivesDelayBoundary() {
        client.get().uri("/api/context/delayed")
            .header("X-Request-Id", "req-delay")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.requestId").isEqualTo("req-delay")
                .jsonPath("$.stage").isEqualTo("after-delay");
    }

    @Test
    void contextSurvivesBoundedElasticBoundary() {
        client.get().uri("/api/context/bounded")
            .header("X-Request-Id", "req-bounded")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.requestId").isEqualTo("req-bounded")
                .jsonPath("$.stage").isEqualTo("legacy-stage");
    }

    @Test
    void innerContextOverrideHasLocalScope() {
        client.get().uri("/api/context/scoped")
            .header("X-Request-Id", "external-id")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                "X-Request-Id", "external-id")
            .expectBody()
                .jsonPath("$.requestId")
                    .isEqualTo("local-override")
                .jsonPath("$.stage")
                    .isEqualTo("local-scope");
    }

    @Test
    void invalidInboundIdGetsNewId() {
        client.get().uri("/api/context")
            .header("X-Request-Id", "invalid id with spaces")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.requestId")
                    .value(value -> {
                        String id = String.valueOf(value);
                        assertNotEquals(
                            "invalid id with spaces", id);
                        assertTrue(id.length() >= 30);
                    });
    }

    @Test
    void errorKeepsCorrelationHeader() {
        client.get().uri("/api/context/error")
            .header("X-Request-Id", "req-error")
            .exchange()
            .expectStatus().isBadRequest()
            .expectHeader().valueEquals(
                "X-Request-Id", "req-error");
    }

    @Test
    void sseEventsKeepSameSubscriptionContext() {
        FluxExchangeResult<ServerSentEvent<TraceReply>> result =
            client.get().uri("/api/context/events")
                .header("X-Request-Id", "req-stream")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .returnResult(new ParameterizedTypeReference<
                    ServerSentEvent<TraceReply>>() {});

        StepVerifier.create(result.getResponseBody())
            .expectNextMatches(event ->
                event.data() != null &&
                "req-stream".equals(event.data().requestId()) &&
                "event-0".equals(event.data().stage()))
            .expectNextMatches(event ->
                event.data() != null &&
                "req-stream".equals(event.data().requestId()) &&
                "event-1".equals(event.data().stage()))
            .expectNextMatches(event ->
                event.data() != null &&
                "req-stream".equals(event.data().requestId()) &&
                "event-2".equals(event.data().stage()))
            .verifyComplete();
    }

    @Test
    void twoHttpRequestsHaveDifferentContext() {
        client.get().uri("/api/context")
            .header("X-Request-Id", "client-A")
            .exchange()
            .expectStatus().isOk()
            .expectBody().jsonPath("$.requestId")
                .isEqualTo("client-A");

        client.get().uri("/api/context")
            .header("X-Request-Id", "client-B")
            .exchange()
            .expectStatus().isOk()
            .expectBody().jsonPath("$.requestId")
                .isEqualTo("client-B");
    }

    @Test
    void missingRouteIs404() {
        client.get().uri("/api/context/not-mapped")
            .exchange()
            .expectStatus().isNotFound();
    }
}
```

There are **9 WebTestClient test methods**. The SSE test actually consumes 3 events rather than checking Content-Type alone. The A/B test above runs sequentially—confirming context is not kept as a singleton from the previous request; to test **true concurrency**, see the `StepVerifier` merge test below.

**Do not assert fixed `threadName` values**, since the project must run reliably across different OSes/CPUs/schedulers. When testing context across an actual network/proxy runtime, add parallel HTTP load and trace ID log instrumentation checks.

## 13. Tests: StepVerifier Verifying Context Semantics Independently of WebFlux HTTP

File `src/test/java/example/ContextOperatorsTest.java`:

```java
package example;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

class ContextOperatorsTest {

    private static final String KEY = "test.trace";

    @Test
    void contextWriteIsVisibleUpstream() {
        Mono<String> source = Mono.deferContextual(ctx ->
            Mono.just(ctx.get(KEY)));

        StepVerifier.create(
                source.contextWrite(Context.of(KEY, "A")))
            .expectNext("A")
            .verifyComplete();
    }

    @Test
    void withoutContextDefaultIsUsed() {
        Mono<String> source = Mono.deferContextual(ctx ->
            Mono.just(ctx.getOrDefault(KEY, "missing")));

        StepVerifier.create(source)
            .expectNext("missing")
            .verifyComplete();
    }

    @Test
    void wrongOperatorPositionDoesNotAffectDownstream() {
        Mono<String> source = Mono.just("x")
            .contextWrite(ctx -> ctx.put(KEY, "inner"))
            .flatMap(value ->
                Mono.deferContextual(ctx ->
                    Mono.just(ctx.getOrDefault(KEY, "missing"))));

        StepVerifier.create(source)
            .expectNext("missing")
            .verifyComplete();
    }

    @Test
    void rightOperatorPositionIsVisibleToFlatMap() {
        Mono<String> source = Mono.just("x")
            .flatMap(value ->
                Mono.deferContextual(ctx ->
                    Mono.just(ctx.getOrDefault(KEY, "missing"))))
            .contextWrite(ctx -> ctx.put(KEY, "A"));

        StepVerifier.create(source)
            .expectNext("A")
            .verifyComplete();
    }

    @Test
    void nearestUpstreamContextWriteWinsForSameKey() {
        Mono<String> source =
            Mono.deferContextual(ctx -> Mono.just(ctx.get(KEY)))
                .contextWrite(ctx -> ctx.put(KEY, "inner"))
                .contextWrite(ctx -> ctx.put(KEY, "outer"));

        StepVerifier.create(source)
            .expectNext("inner")
            .verifyComplete();
    }

    @Test
    void contextSurvivesPublishOn() {
        Mono<String> source =
            Mono.just("start")
                .publishOn(Schedulers.parallel())
                .flatMap(value ->
                    Mono.deferContextual(ctx ->
                        Mono.just(value + "-" + ctx.get(KEY))))
                .contextWrite(Context.of(KEY, "X"));

        StepVerifier.create(source)
            .expectNext("start-X")
            .verifyComplete();
    }

    @Test
    void contextSurvivesDelay() {
        Mono<String> source = Mono.delay(Duration.ofMillis(5))
            .flatMap(tick ->
                Mono.deferContextual(ctx ->
                    Mono.just(ctx.get(KEY))))
            .contextWrite(Context.of(KEY, "delayed"));

        StepVerifier.create(source)
            .expectNext("delayed")
            .verifyComplete();
    }

    @Test
    void separateSubscriptionsAreIsolated() {
        Mono<String> source =
            Mono.deferContextual(ctx -> Mono.just(ctx.get(KEY)));

        Flux<String> merged = Flux.merge(
            source.contextWrite(Context.of(KEY, "A"))
                .subscribeOn(Schedulers.parallel()),
            source.contextWrite(Context.of(KEY, "B"))
                .subscribeOn(Schedulers.parallel()));

        StepVerifier.create(merged.collectList())
            .expectNextMatches(list ->
                list.size() == 2 &&
                list.contains("A") &&
                list.contains("B"))
            .verifyComplete();
    }

    @Test
    void innerFlatMapContextDoesNotRewriteSibling() {
        Mono<String> source = Mono.just("hello")
            .flatMap(word ->
                Mono.deferContextual(ctx ->
                    Mono.just(word + "-" + ctx.get(KEY)))
                    .contextWrite(Context.of(KEY, "inner")))
            .flatMap(value ->
                Mono.deferContextual(ctx ->
                    Mono.just(value + "-" + ctx.get(KEY))))
            .contextWrite(Context.of(KEY, "outer"));

        StepVerifier.create(source)
            .expectNext("hello-inner-outer")
            .verifyComplete();
    }

    @Test
    void manyFluxEventsSeeContext() {
        Flux<String> source = Flux.range(0, 3)
            .concatMap(index -> Mono.deferContextual(ctx ->
                Mono.just(ctx.get(KEY) + ":" + index)))
            .contextWrite(Context.of(KEY, "stream-A"));

        StepVerifier.create(source)
            .expectNext("stream-A:0", "stream-A:1",
                "stream-A:2")
            .verifyComplete();
    }

    @Test
    void innerOverrideAffectsOnlyInnerPublisher() {
        Mono<String> base =
            Mono.deferContextual(ctx -> Mono.just(ctx.get(KEY)));

        Mono<String> source = base
            .contextWrite(Context.of(KEY, "inner"));

        StepVerifier.create(
            source.contextWrite(Context.of(KEY, "outer")))
            .expectNext("inner")
            .verifyComplete();

        StepVerifier.create(
            base.contextWrite(Context.of(KEY, "outer")))
            .expectNext("outer")
            .verifyComplete();
    }

    @Test
    void missingRequiredKeyIsAnError() {
        Mono<String> source =
            Mono.deferContextual(ctx -> Mono.just(ctx.get(KEY)));

        StepVerifier.create(source)
            .expectError(java.util.NoSuchElementException.class)
            .verify();
    }
}
```

There are **12 Reactor unit tests**. Results do not depend on Netty thread names; `StepVerifier` verifies exact values, completion, and missing contexts. `separateSubscriptionsAreIsolated` merges two pipelines on the same scheduler, confirming both A and B appear even though completion order may vary—demonstrating concurrency better than sequential HTTP calls alone.

### 13.1. When to Use StepVerifier.withVirtualTime?

When testing multi-minute streams with `delayElements`/`interval`, a virtual scheduler is faster and more reliable than `Thread.sleep`. Build the publisher **inside the `Supplier`** passed to `withVirtualTime`:

```java
@Test
void virtualTimeStillPreservesContext() {
    StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofHours(1))
            .take(2)
            .concatMap(n ->
                Mono.deferContextual(ctx ->
                    Mono.just(ctx.get("trace") + ":" + n)))
            .contextWrite(Context.of("trace", "virtual")))
        .expectSubscription()
        .thenAwait(Duration.ofHours(2))
        .expectNext("virtual:0", "virtual:1")
        .verifyComplete();
}
```

Additional snippet for `ContextOperatorsTest` using its existing imports. With `withVirtualTime`, never create `Flux.interval` outside the `Supplier` before verifying, because the scheduler may already be captured before the virtual scheduler is installed.

## 14. Passing Context to Non-Reactor Callbacks

### 14.1. CompletableFuture

```java
CompletableFuture<String> future =
    CompletableFuture.supplyAsync(
        () -> legacyService.readData());
```

This uses another executor and does not inherently have Reactor subscriber context. Wrapping it:

```java
Mono<String> wrapped = Mono.fromFuture(future);
```

gives a reactive result without automatically giving `supplyAsync` (which already started) the context. If reading context matters, read via `deferContextual` and pass an **immutable request ID** into the supplier, or use a standard context-propagating executor.

### 14.2. Scheduler Wrappers, Micrometer ContextSnapshot

For non-Reactor executors and `ThreadLocal`-dependent libraries, use `io.micrometer:context-propagation` to register accessors/capture snapshots when needed, wrapping execution per the version's API. Never "set `ThreadLocal` and forget to restore" since thread pools reuse threads. Restore strictly within a **scope** and close/clear in `finally`/`try-with-resources`.

### 14.3. Coroutines

Spring WebFlux with Kotlin coroutines can bridge Reactor Context to coroutine context via proper integrations (e.g., `ReactorContext`), though never assume every Java `ThreadLocal` survives suspension by default. Before porting Java Reactor code to Kotlin, verify coroutine context propagation/`withContext` boundaries and framework dependencies.

### 14.4. Reactive Transaction Boundaries

A Spring reactive transaction holds connection/transaction state in reactive context. Manually calling `subscribe()` on an isolated `repository.save()` can escape the transaction/subscription and commit at unexpected times. Compose publishers inside the transaction chain using `TransactionalOperator` or properly configured reactive `@Transactional`.

## 15. Security, Privacy, and Logging Hygiene

While Reactor Context is great for auditing/tracing, never turn it into a dumping ground for all user state.

### 15.1. Metadata Classification

| Category | Usable in Context? | Notes |
| --- | --- | --- |
| Validated correlation/request ID | Yes | Logs/tracing only, not authentication |
| Span/observation context | Yes via instrumentation | Let Micrometer/OpenTelemetry manage it |
| Authenticated principal | Spring Security reactive context | Never trust `X-User` headers |
| Tenant ID | Only from trusted sources | Must still authorize per resource |
| Locale/timezone preference | Possibly | Choose clear source and validation |
| Raw JWT/password/session cookie | Avoid | Can leak via context dumps/logs |
| Large request body/`FilePart` | Avoid | Buffer/memory/resource bloat |
| Mutable JPA `EntityManager` | Unsuitable | Blocking/thread-bound semantics |
| Mutable global `Map` state | No | Data race/leak risks |

### 15.2. Client-Supplied IDs: Authentication or Correlation Only?

A `requestId` header can be spoofed, reused, or contain unsuitable input. The demo only validates an allowlist pattern and echoes it. Production needs rules on length, uniqueness, log forging, trusted ingress trace correlation, and sampling. Never use `requestId` for access control or idempotency keys without validating scope.

### 15.3. Tracing Over the Network

Reactor Context stays **in-process/in-JVM**. When WebClient calls a remote service, the remote JVM cannot automatically read this Context. Distributed tracing uses HTTP propagation conventions like W3C `traceparent` and instrumentation. Never dump an entire `ContextView` to debug logs since it may contain internal keys from security/tracing libraries.

### 15.4. Correlation Logs and HTTP Errors

When an error hits mid-SSE stream, the correlation ID helps locate logs for that request. Yet the response may already have committed 200 with no way to change status; correlation does not replace a business failure protocol. Error logs need proper severity, structured error codes, and zero leaked tokens/PII.

## 16. Common Pitfalls to Recognize

| Misconception / Symptom | Cause | Right Approach |
| --- | --- | --- |
| "`ThreadLocal` always survives in WebFlux" | Publishers switch schedulers/threads | Use Reactor Context or a bridge |
| "Each request gets its own Netty thread" | Event loops serve many channels | Never rely on thread identity |
| "Context is just a global map" | Attached to subscriber | Read via `deferContextual` |
| "`contextWrite` mutates Context in place" | Context is immutable | Return new Context along the chain |
| "`contextWrite` affects every operator below it" | Propagation flows upward | Place `contextWrite` downstream of readers |
| "Context placed at source is read by downstream `flatMap`" | `contextWrite` scope is upstream only | Test ordering with `StepVerifier` |
| "`Mono.just(ctx.get(...))` in controller gets current context" | No per-subscription ctx in imperative code | `deferContextual` |
| "A static `String requestId` works for everyone" | Cross-request race/leak | Per-subscriber Context |
| "Inner branch Context affects all siblings" | Overrides are locally scoped | Place write at common downstream if needed |
| "Manual `subscribe()` keeps HTTP context" | Creates a separate subscription | Compose publishers / return chain |
| "`publishOn` loses Reactor Context" | Usually not when pipeline is valid | `deferContextual` across operator |
| "`publishOn` propagates all `ThreadLocal`s" | `ThreadLocal` differs from Context | Registered accessor/bridge |
| "Enabling auto hook restores every `ThreadLocal`" | Missing SPI/accessor | Configure Micrometer properly |
| "Default mode restores MDC in every `map`" | Limited restoration | Check `handle`/`tap`/automatic mode |
| "`contextCapture` reads Context and writes `ThreadLocal`" | Usually captures registered `ThreadLocal` into Context | Understand capture/restore direction |
| "`WebFilter` setting `ThreadLocal` suffices for long SSE" | Thread lifetimes change | `WebFilter` `contextWrite` |
| "Globally shared SSE Flux gets per-client Context automatically" | Upstream hot sharing is subtle | Read context per-client downstream |
| "Reactive Context auto-sends to remote microservices" | Local to JVM/subscription | Explicit tracing/outbound headers |
| "Missing Context falls back to admin" | Auth bypass | Fail closed |
| "`X-Request-Id` is user identity" | Client-modifiable header | Trusted auth principal |
| "`MDC.put` doesn't need `remove`" | Threads are reused | `try/finally` or integration |
| "Dumping entire Context to logs is safe" | May contain sensitive metadata | Log allowlisted keys only |
| "Every blocking call auto-routes to `boundedElastic`" | Reactor doesn't rewrite library code | Explicit bridge/non-blocking driver |
| "Context makes Flux faster" | Carries metadata only | Optimize source/backpressure separately |
| "Failed HTTP 200 stream can switch to 500" | Headers already committed | Protocol error/cancel |
| "`WebTestClient` asserting `threadName` proves isolation" | Unstable runtime detail | Assert `requestId` and test scheduler hops |
| "String context keys never collide" | Libraries/apps may share names | Namespaces/object keys |
| "`cache()` Context is always isolated per subscriber" | Shared sources have separate lifecycles | Understand hot/cold/cache semantics |
| "Request context equals transaction" | Separate business transaction APIs | Reactive transaction infrastructure |
| "Context is `HttpSession`" | Subscription-scoped, not durable | Use proper session stores |

## 17. Pre-Production Checklist

1. [ ] Explicitly define which metadata must propagate (correlation ID, trusted principal ref, trace).
2. [ ] Zero static mutable request state or unbridged/uncleaned `ThreadLocal`s.
3. [ ] Context keys are stable, namespaced, or typed identity objects.
4. [ ] `contextWrite` placed downstream of intended readers.
5. [ ] `deferContextual` used properly at subscription time.
6. [ ] Zero manual `subscribe()` calls for side effects outside the request chain.
7. [ ] Context tested across scheduler switches via `publishOn`/`subscribeOn`.
8. [ ] Context tested across inner publishers and sibling branches.
9. [ ] For SSE/streaming, multiple events verified to carry the same context.
10. [ ] Resources cleaned up on complete/error/cancel; not relying solely on `doOnComplete`.
11. [ ] If using MDC/`ThreadLocal`, Micrometer accessors and automatic/default modes explicitly configured.
12. [ ] Auto context propagation not enabled blindly "just in case"; overhead measured.
13. [ ] Spring Security principal/tenant derived from trusted auth, never from request ID headers.
14. [ ] Outbound WebClient tracing/correlation propagated via controlled headers.
15. [ ] DB transactions use reactive transaction APIs, never faked via context keys.
16. [ ] Secrets never logged/copied and full context never dumped.
17. [ ] Backpressure, buffering, timeouts, and long-lived connections bounded.
18. [ ] `StepVerifier` tests cover missing/override/parallel context isolation.
19. [ ] `WebTestClient` verifies headers/bodies/errors/SSE across scheduler boundaries.
20. [ ] Request trace/log correlation observed under concurrent load.

## 18. Review Questions and Answers

**1.** Does Reactor Context attach to a thread or a subscriber?  
**Answer:** Subscriber/subscription, not a Java Thread.

**2.** In which direction does `contextWrite` propagate values?  
**Answer:** Toward upstream operators when the subscription is established.

**3.** Why use `deferContextual`?  
**Answer:** To read context when the Publisher is subscribed rather than at assembly time.

**4.** Does `ContextView` have a mutable `set()`?  
**Answer:** No; it is a read-only view.

**5.** Does `Context.put` mutate the original instance?  
**Answer:** No, it returns a new `Context`.

**6.** Can `ThreadLocal` be used in synchronous MVC?  
**Answer:** Yes, when scope and cleanup are properly managed; never extrapolate that to WebFlux.

**7.** Does `publishOn` erase Reactor Context?  
**Answer:** No; in a properly composed Reactor chain, context stays with the subscription.

**8.** Is `ThreadLocal.get()` after `publishOn` guaranteed to read the right request?  
**Answer:** No, unless a properly configured context propagation bridge is present.

**9.** Does automatic mode propagate an arbitrary unregistered `ThreadLocal`?  
**Answer:** No; `ThreadLocalAccessor`/context-propagation integration is required.

**10.** What does `contextCapture()` primarily do?  
**Answer:** Captures registered `ThreadLocal` values at subscription time into Reactor Context.

**11.** Why shouldn't you manually `subscribe()` inside a WebFlux handler?  
**Answer:** Creating a detached subscription can lose context, cancellation, error handling, and transaction scope.

**12.** Should `X-Request-Id` be used as role or tenant authority?  
**Answer:** No; it is untrusted correlation metadata unsuitable for authorization.

**13.** If an SSE Flux emits three events, are there three separate Contexts?  
**Answer:** Typically one subscription context for that client, unless inner branches intentionally override it.

**14.** Does an inner `flatMap` publisher writing context change context app-wide?  
**Answer:** No, inner context writes are locally scoped.

**15.** What caution is needed when using a global shared Flux for per-user private data?  
**Answer:** Upstream sharing may not preserve per-subscriber context/tenant boundaries; isolate scopes and authorization.

**16.** How do you pass a correlation ID to a remote HTTP service?  
**Answer:** Read Context and set an outbound header per policy, or use tracing instrumentation.

**17.** What is `ReactiveSecurityContextHolder` for?  
**Answer:** Accessing Spring Security's authentication context inside a reactive chain.

**18.** Does Context automatically create a DB transaction?  
**Answer:** No; reactive transaction infrastructure is required.

**19.** Why does MDC need cleanup on thread pools?  
**Answer:** Threads are reused, so stale state can leak into other requests.

**20.** How do you test context without relying on `threadName`?  
**Answer:** `StepVerifier` `expectNext` values and `WebTestClient` HTTP IDs across scheduler hops.

**21.** Does Context affect HTTP status after the response is committed?  
**Answer:** No, it only carries metadata.

**22.** If a `contextWrite` closer to the source writes the same key as downstream, which wins?  
**Answer:** The one closer to the source overrides the downstream value for the source.

**23.** If a required context key is missing, what does `ctx.get(key)` do?  
**Answer:** Normally throws `NoSuchElementException`; handle fail-closed or per explicit policy.

**24.** Does `spring.reactor.context-propagation=auto` create a security principal?  
**Answer:** No, it only configures propagation for registered `ThreadLocal` integrations.

**25.** When a user cancels SSE, which signal should cleanup watch?  
**Answer:** `SignalType.CANCEL` via `doFinally`/appropriate lifecycle hooks rather than waiting for completion.

## 19. Official References

- [Project Reactor 3.6 Reference — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/3.6.12/reference/index.html#context): per-subscriber Context mechanism, `contextWrite`, `deferContextual`, operator order, and inner scopes.
- [Project Reactor — Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html): Micrometer context-propagation, default/automatic modes, `ThreadLocalAccessor`, `contextCapture`.
- [Project Reactor — Mono Javadoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): `deferContextual`, `contextWrite`, subscription and operator behavior.
- [Project Reactor — Flux Javadoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `Flux.deferContextual`, schedulers, and error/cancellation operators.
- [Spring Framework 6.2 — WebFlux WebHandler API](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/web-handler-api.html): `WebFilter`, `ServerWebExchange`, reactive request lifecycle.
- [Spring Boot — Observability and Context Propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html): Reactor context-propagation auto setting and Micrometer integration.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): reactive security context/authorization.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html): reactive HTTP tests.
- [Reactor Test StepVerifier Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): signal/value/time tests.

**Key takeaway:** ***ThreadLocal belongs to a thread; Reactor Context belongs to a subscriber.*** In WebFlux streams, to pass request IDs/traces/locales across async boundaries, write to Context with `contextWrite` and read with `deferContextual` in the right scope. When MDC or `ThreadLocal`-based libraries are needed, use Micrometer context-propagation/registered accessors explicitly—never assume Reactor Context automatically makes every `ThreadLocal` safe. And always keep correlation metadata separate from authentication/authorization.
