# Subscription-Bound `Context` and `ContextView` in Project Reactor

## 1. Why Does Reactor Need Context?

In Spring WebFlux, a reactive processing pipeline can pass through many operators, run across multiple worker threads, and serve many HTTP requests concurrently. Business data such as `User` or `Order` should be passed explicitly via `onNext`, whereas certain **auxiliary metadata** needs to be available across layers: correlation IDs, tracing metadata, non-sensitive request info, and library context.

In synchronous programming, people commonly use `ThreadLocal`. That approach is error-prone in reactive code: **one subscription can switch threads, and one thread can serve many subscriptions**. Reactor provides a dedicated mechanism:

- **`Context`**: an **immutable** key/value store that lets you produce new versions via `put`, `delete`, and `putAll`.
- **`ContextView`**: a **read-only** interface for viewing and extracting data from a Context.
- **`contextWrite(...)`**: adds to or transforms the Context at **subscription time**; affects operators **upstream**.
- **`Mono.deferContextual(...)` / `Flux.deferContextual(...)`**: reads the subscription's `ContextView` at the moment the source needs to be created.
- **Each subscription has its own context**: the same publisher can be subscribed to multiple times with different Context data without mutating the original publisher.

This lesson is about **context scoping**, not how to store a global variable. `Context` is not a copy of an HTTP session, not a Java `ThreadLocal`, not sent automatically over the network, and not a `Map` you mutate in place.

## 2. Mental Model: Context Follows the Subscriber, Not the Thread

Consider this pipeline:

~~~java
Mono<String> greeting = Mono.deferContextual(ctx ->
    Mono.just("Hello " + ctx.getOrDefault("user", "guest"))
);

Mono<String> forMai = greeting.contextWrite(
    Context.of("user", "Mai")
);
~~~

This is a Java snippet (requires importing `Mono` and `Context`). Merely declaring the variables does not trigger a subscription, so Context is not read yet. When a subscriber subscribes to `forMai`:

~~~text
Assembly:    create greeting -------- create contextWrite -------- no data yet

Subscription:
  final subscriber
          |
          v
    contextWrite("user"="Mai")      <-- creates new Context for upstream
          |
          v
    deferContextual(ctx)           <-- reads ContextView: user=Mai
          |
          v
    Mono.just("Hello Mai")
          |
          v
   final subscriber receives onNext / onComplete
~~~

Context is stored and retrieved through the **Subscriber chain**. When an operator needs to read it, it obtains the Context from the subscriber **downstream** of itself. Thus, Context data is **propagated upstream during the subscription phase**, in the opposite direction of `onNext` signals emitted **from upstream to downstream**.

There are three key consequences:

1. A publisher does not have a single fixed global Context; **Context is bound to the subscription** (and to the subscribers along the operator chain).
2. A `contextWrite` placed below a read site will be visible to operators above it. Writing above and reading below does not work in reverse.
3. Switching threads with `publishOn` or `subscribeOn` **does not erase the Context** of a properly connected Reactor chain. It does not depend on whether the previous thread held any `ThreadLocal` values.

**Distinction to keep in mind:** Context carries **metadata** per subscription, whereas business items travel through `onNext`. Context is not an alternative event channel.

## 3. `Context` and `ContextView` APIs

Both hold `Object key → Object value` pairs. `Context` **extends** `ContextView`, so a `Context` can be passed to an API that only accepts `ContextView`. Conversely, a `ContextView` has no methods to modify values.

| API | Available on | Meaning |
| --- | --- | --- |
| `Context.empty()` | `Context` factory | Creates an empty Context |
| `Context.of(key, value)` | `Context` factory | Creates a Context pre-populated with data |
| `put(key, value)` | `Context` | Returns a **new Context** with the key/value added or replaced |
| `delete(key)` | `Context` | Returns a **new Context** without the key |
| `putAll(contextView)` | `Context` | Returns a new Context with merged data |
| `get(key)` | `ContextView` | Retrieves the value; throws `NoSuchElementException` if the key is missing |
| `getOrDefault(key, fallback)` | `ContextView` | Returns the value if present, otherwise returns fallback |
| `getOrEmpty(key)` | `ContextView` | Returns `Optional<T>` |
| `hasKey(key)` | `ContextView` | Checks whether the key exists |
| `size()`, `stream()` | `ContextView` | Inspects the number of pairs and existing entries |

**Immutability:**

~~~java
Context original = Context.of("traceId", "T-01");
Context updated = original.put("traceId", "T-02");

System.out.println(original.get("traceId")); // T-01
System.out.println(updated.get("traceId"));  // T-02
~~~

`put` **does not mutate `original`**; it returns a new Context object. If you forget to assign the return value of `put`, the original instance stays unchanged:

~~~java
Context ctx = Context.empty();
ctx.put("traceId", "T-01");          // creates a new Context but does not use it
System.out.println(ctx.hasKey("traceId")); // false
~~~

**Keys and values:** Do not use `null` as a key or value in `Context`. When data may be missing, choose `getOrDefault`, `getOrEmpty`, or an explicit error policy. Prefer descriptive namespaced keys, such as `"app.traceId"`, to reduce collisions with other libraries. When type safety is needed, use a dedicated application-managed key object and a clear record/type as the value.

**Security note:** Context can carry metadata needed for internal processing, but it does not replace authentication, authorization, or trust boundary checks. Do not log the entire Context if it contains tokens or PII.

## 4. `contextWrite`: Write Downstream for Upstream to Read

Two common overloads:

~~~java
Mono<String> a = source.contextWrite(
    Context.of("app.traceId", "T-01")
);

Mono<String> b = source.contextWrite(
    ctx -> ctx.put("app.traceId", "T-01")
);
~~~

These are snippets assuming `source` is a `Mono<String>`:

- `contextWrite(ContextView)` merges the passed Context with the current downstream Context and exposes the new Context **upstream**; entries from `ContextView` are layered on top and can overwrite matching keys.
- `contextWrite(Function<Context,Context>)` receives the current Context at subscription time and returns a new Context, typically via `ctx.put(...)`.
- `contextWrite(...)` **does not emit a data item**, does not call `subscribe()`, and does not turn a publisher into a hot publisher.
- Context is applied by **operator position**; there is no "JVM-wide global put."

Correct example:

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
    Mono.just(ctx.get("app.traceId"))
).contextWrite(ctx -> ctx.put("app.traceId", "T-01"));
~~~

A subscriber to `result` receives `"T-01"`. Because `contextWrite` sits **below** `deferContextual`, the read step can see the key.

Example where it is not visible because `contextWrite` is placed on the wrong side:

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
    Mono.just("upstream=" + ctx.getOrDefault("app.traceId", "-"))
)
.contextWrite(ctx -> ctx.put("app.traceId", "T-01"))
.flatMap(value -> Mono.deferContextual(ctx ->
    Mono.just(value + "; downstream="
        + ctx.getOrDefault("app.traceId", "-"))
));
~~~

When subscription begins with an empty Context, the output is `upstream=T-01; downstream=-`. In the `flatMap` **after** `contextWrite`, the reader cannot see a Context that was only propagated **upstream** into the earlier section.

Rule of thumb: **read near the source, write from the subscriber side**. Trace operator positions in the chain rather than guessing that Context "travels with `onNext`."

## 5. Two Writes to the Same Key: Which Value Wins?

Consider:

~~~java
Mono<String> message = Mono.deferContextual(ctx ->
    Mono.just(ctx.get("env"))
)
.contextWrite(ctx -> ctx.put("env", "near"))
.contextWrite(ctx -> ctx.put("env", "far"));
~~~

Subscription starts from the bottom:

1. `contextWrite(... "far")` creates a Context containing `env=far`.
2. As subscription moves toward the source, `contextWrite(... "near")` receives the existing Context and produces a new Context containing `env=near`.
3. `deferContextual` at the top reads `env=near`.

Therefore, the result is **`near`**, not `far`. When multiple writes target the same key, **the write closer to the reader on the upstream side** is the one the reader sees.

This is not a race condition or a mutable variable "being overwritten in turn": two operators produce two immutable Context versions, and the reader obtains the Context provided by the subscriber immediately below it.

Another case: if you only use `contextWrite(Context.of(...))` to add keys, non-overwritten keys remain in the merged result. Do not build a completely fresh Context inside `contextWrite(ctx -> Context.empty().put(...))` unless you intentionally want to wipe out all existing downstream metadata; doing so can break tracing, security, or other library contexts.

## 6. Complete Java 17+ Program: Proving Context Is Bound to Each Subscription

This section uses Project Reactor Core and Gradle. The example deliberately prints **Context values**, not thread names or timing, so the output is deterministic.

Create `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.6'
}

application {
    mainClass = 'ContextSubscriptionDemo'
}
~~~

Create `src/main/java/ContextSubscriptionDemo.java`:

~~~java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

public final class ContextSubscriptionDemo {
    private static final String USER = "app.user";
    private static final String LABEL = "app.label";

    public static void main(String[] args) {
        Mono<String> greeting = Mono.deferContextual(ctx ->
            Mono.just("hello " + ctx.getOrDefault(USER, "guest"))
        );

        System.out.println("without context=" + greeting.block());

        System.out.println("first=" +
            greeting.contextWrite(Context.of(USER, "Mai")).block());

        System.out.println("second=" +
            greeting.contextWrite(Context.of(USER, "An")).block());

        Mono<String> precedence = Mono.deferContextual(ctx ->
            Mono.just(ctx.<String>get(LABEL))
        )
        .contextWrite(ctx -> ctx.put(LABEL, "near"))
        .contextWrite(ctx -> ctx.put(LABEL, "far"));

        System.out.println("precedence=" + precedence.block());

        Mono<String> visibility = Mono.deferContextual(ctx ->
                Mono.just("upstream=" +
                    ctx.getOrDefault(LABEL, "-"))
            )
            .contextWrite(ctx -> ctx.put(LABEL, "inside"))
            .flatMap(text -> Mono.deferContextual(ctx ->
                Mono.just(text + ", downstream=" +
                    ctx.getOrDefault(LABEL, "-"))
            ));

        System.out.println("visibility=" + visibility.block());

        Mono<String> nested = Mono.deferContextual(ctx ->
                Mono.just("outer=" + ctx.get(LABEL))
            )
            .flatMap(text -> Mono.deferContextual(ctx ->
                Mono.just(text + ", inner=" + ctx.get(LABEL))
            ).contextWrite(ctx -> ctx.put(LABEL, "inner-value")))
            .contextWrite(ctx -> ctx.put(LABEL, "outer-value"));

        System.out.println("nested=" + nested.block());
    }
}
~~~

Run with `gradle run --quiet` or `./gradlew run --quiet` if the project has a Gradle Wrapper. Deterministic stdout:

~~~text
without context=hello guest
first=hello Mai
second=hello An
precedence=near
visibility=upstream=inside, downstream=-
nested=outer=outer-value, inner=inner-value
~~~

**Points to observe:**

- The same `greeting` pipeline was assembled once, yet two subscriptions with `Context.of(USER, "Mai")` and `Context.of(USER, "An")` **read two different values**.
- Without `contextWrite`, `getOrDefault` returns `guest`. Avoid `ctx.get(USER)` if the key is optional.
- Two writes to the same key in `precedence`: the reader sees `near` (closer to the reader).
- `visibility` proves that Context from `contextWrite` is only visible upstream.
- `nested` proves that Context written **inside an inner publisher of `flatMap`** affects the inner publisher while the outer Context remains `outer-value`; the inner write does not alter the outer Context value.

**`block()` is used only in the console `main` demo.** It creates a subscription and blocks the calling thread to wait for the result; do not use `block()` in a reactive WebFlux controller. The demo's purpose is to verify Context semantics accurately, not to recommend blocking in applications.

## 7. Context Does Not Belong to a Publisher Variable and Is Not Shared Across Subscribers

Some people write:

~~~java
Mono<String> source = Mono.deferContextual(ctx ->
    Mono.just(ctx.getOrDefault("id", "missing"))
);
~~~

and assume `source` holds a shared `Context` field that can be set/get from anywhere. That is **wrong**: `source` is a pipeline blueprint; concrete Context values are provided per **downstream subscription**.

~~~java
Mono<String> a = source.contextWrite(Context.of("id", "A"));
Mono<String> b = source.contextWrite(Context.of("id", "B"));
~~~

If `a` and `b` are subscribed to, each subscription reads the value supplied by its own branch. Even if a scheduler runs on the same thread or two subscriptions interleave, Reactor does not rely on `ThreadLocal` to distinguish A from B.

This is why Context fits **per-request correlation IDs**, as long as each request creates its own subscription chain. It is also why you must never cache a `ContextView` "read in request A" into a `static` field for use in request B: doing so breaks metadata isolation.

### Note on `cache()`, `share()`, and Hot Publishers

Context semantics depend on **actual subscriptions**. Operators like `cache()` or `share()` can cause multiple downstream subscribers to share a single upstream subscription or a cached result:

- With a regular **cold publisher**, each downstream subscribe can trigger its own upstream execution.
- With a `cache()`d publisher, upstream may already have executed under the Context of **the subscriber that triggered caching**; later subscribers simply read the cached result without causing upstream to re-read their Context.
- With a hot source emitting data outside the lifecycle of a specific subscriber, you cannot assume the producer holds "the current subscriber's Context."

Avoid placing request- or user-specific data into a **globally cached/shared** pipeline if it could leak results across requests. Context is not a data-protection mechanism when you intentionally share a publisher or result across subscriptions.

## 8. Reading Context at the Source, Mid-Chain, and Inside `flatMap`

### 8.1. Reading When Creating the Source: `deferContextual`

~~~java
Mono<String> audit = Mono.deferContextual(ctx -> {
    String traceId = ctx.getOrDefault("app.traceId", "unknown");
    return Mono.just("trace=" + traceId);
});
~~~

This is a snippet. `deferContextual` invokes the factory only upon subscription and provides a `ContextView` matching the subscription at that position. You can use `Flux.deferContextual(...)` when you need to return a `Flux<T>`.

### 8.2. Reading Mid-Chain: `transformDeferredContextual`

When you already have a `Flux<T>` and need to read metadata in order to construct a transformation branch at subscription time:

~~~java
Flux<String> output = Flux.just("a", "b")
    .transformDeferredContextual((source, ctx) -> {
        String prefix = ctx.getOrDefault("app.prefix", "x");
        return source.map(value -> prefix + ":" + value);
    })
    .contextWrite(Context.of("app.prefix", "trace"));
~~~

This is a snippet requiring imports for `Flux` and `Context`. When subscribed to, the output is `trace:a` followed by `trace:b`. `transformDeferredContextual` receives both the current publisher and a `ContextView`, allowing you to tailor the transformation to subscription metadata. Unlike regular `transform`, which constructs the transformation at assembly time, the `DeferredContextual` variant obtains Context at subscription time.

### 8.3. Reading Inside `flatMap`

~~~java
Mono<String> output = Mono.just("data")
    .flatMap(data -> Mono.deferContextual(ctx -> {
        String trace = ctx.getOrDefault("app.traceId", "missing");
        return Mono.just(data + ":" + trace);
    }))
    .contextWrite(Context.of("app.traceId", "T-01"));
~~~

Upon subscription, the output is `data:T-01`. Because the inner publisher is joined into the Reactor chain at subscription time, `deferContextual` inside the inner publisher can read the Context propagated into that branch.

**Important:** Writing Context inside **an inner publisher** only alters the context visible **inside that inner publisher**; it does not "push" context outward so that sibling operators or the outer pipeline see it. The demo in section 6 with `nested=...` demonstrates this exact behavior.

## 9. Read-Only Nature of `ContextView`

When a library needs a correlation ID to add an HTTP header or enrich logs, the library should normally **only read** metadata. A library's API can accept `ContextView` instead of `Context` so it does not imply permission to mutate the context.

~~~java
static String describe(reactor.util.context.ContextView view) {
    return view.getOrDefault("app.traceId", "no-trace");
}
~~~

This is a method snippet. `ContextView` **has no `put` or `delete`**. If you need to transform Context for upstream, do so explicitly at a `contextWrite` site; do not try to force `ContextView` into a mutable `Map`.

Conceptually:

- `Context` represents the ability to create a **new version of context data**.
- `ContextView` represents the ability to **observe** current context data.
- The Context object itself is immutable; however, **a value inside it may be a mutable object**. If you store an `ArrayList`/`HashMap` and mutate it, you can introduce unsafe shared state. Prefer `String`, numbers, records/immutable values; if you must use a mutable object, you must design its thread safety and lifetime yourself.

Do not rely on a generic cast on `ctx.get("key")` without checking the library's contract: keys and values are typed as `Object`, so putting the wrong value type can lead to a `ClassCastException` at the read site. When authoring a library, use consistently defined keys and clear value types.

## 10. `ThreadLocal`, MDC, and Scheduler Switching

Comparison:

| Aspect | `ThreadLocal` | Reactor `Context` |
| --- | --- | --- |
| Scope | Current thread | Subscriber/subscription in a Reactor chain |
| Across thread switches | Does not automatically carry data to a new thread | Context remains accessible via the subscriber across Reactor operators |
| When threads are reused | Old data can linger if cleanup is forgotten | Each subscription's Context is established independently |
| Reading | `threadLocal.get()` | `deferContextual(ctx -> ...)` or Context-reading APIs |
| Writing | `threadLocal.set(...)`, mutates state | `contextWrite(ctx -> ctx.put(...))` creates a new Context |
| Use case | Synchronous thread-bound libraries | Correlation/tracing metadata within Reactor chains |

An example proving that switching workers does not break Context:

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("app.traceId", "none"))
    )
    .publishOn(Schedulers.parallel())
    .map(trace -> "trace=" + trace)
    .contextWrite(Context.of("app.traceId", "T-01"));
~~~

This is a snippet (import `Mono`, `Schedulers`, `Context`). When the subscriber awaits completion, the output is `trace=T-01` despite `publishOn` in the chain. Still, **do not conclude that `ThreadLocal` will automatically carry `T-01` to the new worker**.

**MDC logging:** Many logging frameworks use `ThreadLocal` for MDC. Calling `MDC.put(...)` inside an operator and assuming every subsequent operator will see it on every thread is incorrect. The proper approach depends on Reactor/Micrometer context-propagation versions and configuration mode:

- You can use data from Reactor Context to add correlation IDs right where you log, or build a bridge with cleanup.
- Reactor includes **built-in context-propagation support** when properly installed and configured. Default mode and automatic mode behave differently; never assume adding `contextWrite` always synchronizes all MDC state automatically.
- If transferring data from `ThreadLocal` into Reactor Context, capture timing, operators used, and lifecycle all matter. Always verify the mechanism with tests when using a specific tracing/observability library.

Key takeaway: **Context is a per-subscription data model**; context-propagation for `ThreadLocal` is a separate integration mechanism that may or may not be enabled.

## 11. Spring WebFlux Application: Passing Correlation ID to a Service

Suppose an HTTP handler retrieves the `X-Correlation-ID` header after validation/verification or generates a trustworthy new ID. The service can read the ID from Context without adding a `traceId` parameter to every method.

**Illustrative controller code** (not a standalone program; requires Spring WebFlux, service bean, and imports):

~~~java
@RestController
class GreetingController {
    private final GreetingService service;

    GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/greeting")
    Mono<String> greeting(ServerHttpRequest request) {
        String id = request.getHeaders()
            .getFirst("X-Correlation-ID");

        // In practice: validate/sanitize or generate a trusted ID on the server.
        String correlationId = (id == null || id.isBlank())
            ? "generated-by-server"
            : id;

        return service.greeting()
            .contextWrite(ctx ->
                ctx.put("app.correlationId", correlationId)
            );
    }
}

@Service
class GreetingService {
    Mono<String> greeting() {
        return Mono.deferContextual(ctx -> {
            String id = ctx.getOrDefault(
                "app.correlationId", "unknown"
            );
            return Mono.just("correlationId=" + id);
        });
    }
}
~~~

**Classes/imports**: `org.springframework.web.bind.annotation.RestController`, `GetMapping`, `org.springframework.http.server.reactive.ServerHttpRequest`, `org.springframework.stereotype.Service`, `reactor.core.publisher.Mono`. This example only illustrates Context propagation; production code must not trust unvalidated client headers, and should not use the literal string `"generated-by-server"` as a real ID. You can generate a server-side request ID and enforce length/character policies before logging header values.

**Why place `contextWrite` on the returned publisher?** Spring WebFlux subscribes to the returned `Mono`; the subscription flows back through `contextWrite` to `service.greeting()`, where `deferContextual` obtains the correlation ID. No global/static variable stores IDs across different requests.

What Context **does not do automatically**:

- It does not automatically send `app.correlationId` to another microservice via `WebClient`; you need to add the header or use a standard tracing system with propagation support.
- It does not turn an HTTP header value into trusted information.
- It does not automatically synchronize all `ThreadLocal`/MDC state without proper bridging and configuration.
- It does not replace Spring Security's standard security context storage. Reactive security uses its own mechanism (such as `ReactiveSecurityContextHolder`), so libraries must never assume keys or grant access from a client-supplied Context string.

If you need to attach the ID to an outbound `WebClient` call, you can read Context at request-construction time in an appropriate layer and map it to an HTTP header per your system contract. That is an explicit step to propagate metadata **across a network boundary**, not an automatic property of Reactor Context.

## 12. Context in a Shared Library

An important benefit is that an upstream library can read metadata added by a downstream application **at subscription time**. For example, a service/library implements a publisher that reads a trace ID:

~~~java
public Mono<String> callLibraryOperation(String payload) {
    return Mono.deferContextual(ctx -> {
        String trace = ctx.getOrDefault(
            "app.traceId", "not-provided"
        );
        return Mono.just("payload=" + payload + ", trace=" + trace);
    });
}
~~~

This is a snippet: the method can live inside a library. The caller does not need to change the method signature to pass an extra ID:

~~~java
Mono<String> output = callLibraryOperation("hello")
    .contextWrite(Context.of("app.traceId", "T-42"));
~~~

At subscription time, the library reads `T-42`. This is useful for logging/tracing/correlation, but should not be overused to hide mandatory business dependencies: if a method **needs** `userId` to compute results and validate permissions, consider passing an explicit business request/context object instead of hiding everything in Reactor Context.

When writing a library:

1. Define namespaced keys and clear value types.
2. For optional metadata, use `getOrDefault`/`getOrEmpty` rather than throwing unexpected errors just because a key is absent.
3. If metadata is mandatory, document that requirement clearly in the contract; handle missing keys deliberately.
4. Avoid overwriting keys already defined by frameworks.
5. Do not use Context to hold large datasets or act as a business cache.

## 13. Context in `flatMap`, Sub-Streams, and Composition Boundaries

A pipeline can create **inner publishers**:

~~~java
Mono<String> chain = Mono.just("data")
    .flatMap(value ->
        Mono.deferContextual(ctx ->
            Mono.just(value + ":" + ctx.get("k"))
        ).contextWrite(ctx -> ctx.put("k", "inner"))
    )
    .flatMap(value ->
        Mono.deferContextual(ctx ->
            Mono.just(value + ":" + ctx.getOrDefault("k", "outer-default"))
        )
    )
    .contextWrite(ctx -> ctx.put("k", "outer"));
~~~

When subscribed to, the result is **`data:inner:outer`**:

- The first inner publisher receives a local Context with `k=inner`.
- That local Context exists only inside the first inner publisher; it does not mutate the outer Context.
- The second inner publisher still reads `k=outer` from the outer chain's Context.

Be very careful with code like `flatMap(value -> ...)` combined with `contextWrite`: Context does not ride along with `value`. It is queried through the subscriber at the inner/outer publisher's position, so using Context to "tag" an emitted item's result and expecting a sibling operator to receive that tag is the wrong mental model.

If metadata must **follow each individual item**, such as each record having a different tenant, it is better to put that metadata into an explicit data type like `record Envelope<T>(T value, TenantId tenantId)`, or handle items individually with explicit keys. Context fits **per-subscription** metadata, not per-item varying metadata.

## 14. Retry, Cancellation, and Context

With a cold publisher:

~~~java
Mono<String> operation = Mono.deferContextual(ctx ->
    Mono.just(ctx.getOrDefault("app.traceId", "missing"))
);

Mono<String> retried = operation
    .retry(2)
    .contextWrite(Context.of("app.traceId", "T-01"));
~~~

This is a snippet. If `operation` fails, `retry(2)` can re-subscribe upstream and the subscriber's Context in the appropriate chain remains accessible when building the new subscription. Context **is not a place to store a mutable retry counter**, and `retry` does not guarantee exactly-once execution for side effects. If you need to track state across attempts, use proper bounded state management rather than mutating a value inside Context uncontrollably.

When a subscription is cancelled, the Context attached to it does not have a "global variable that stays alive for other subscribers" lifecycle. A new subscription gets the new subscription's context. Memory reclamation by the runtime/system follows normal Java reference/lifecycle rules; never treat Context as immortal request memory or a session store.

**Relation to `contextCapture`:** In some context-propagation integrations, an operator can capture `ThreadLocal` values registered with that mechanism into Reactor Context at subscription time. That is a dedicated integration tool, not the same thing as `ContextView` or a reason to implicitly expect every `ThreadLocal` to appear in Context automatically.

## 15. Testing with JUnit 5 and StepVerifier

Verify **observable results per subscription**, rather than relying on thread names or execution speed. Keep the Gradle project from section 6; replace the `dependencies` block with:

~~~groovy
dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.6'
    testImplementation 'io.projectreactor:reactor-test:3.8.6'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
}

test {
    useJUnitPlatform()
}
~~~

Create `src/test/java/ContextSubscriptionTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.util.context.Context;

class ContextSubscriptionTest {
    @Test
    void twoSubscriptionsDoNotShareContext() {
        Mono<String> source = Mono.deferContextual(ctx ->
            Mono.just(ctx.getOrDefault("app.user", "guest"))
        );

        StepVerifier.create(
                source.contextWrite(Context.of("app.user", "Mai"))
            )
            .expectNext("Mai")
            .verifyComplete();

        StepVerifier.create(
                source.contextWrite(Context.of("app.user", "An"))
            )
            .expectNext("An")
            .verifyComplete();

        StepVerifier.create(source)
            .expectNext("guest")
            .verifyComplete();
    }

    @Test
    void lastWriteTowardUpstreamWinsForSameKey() {
        Mono<String> source = Mono.deferContextual(ctx ->
                Mono.just(ctx.<String>get("app.flag"))
            )
            .contextWrite(ctx -> ctx.put("app.flag", "near"))
            .contextWrite(ctx -> ctx.put("app.flag", "far"));

        StepVerifier.create(source)
            .expectNext("near")
            .verifyComplete();
    }

    @Test
    void testCanSupplyInitialSubscriberContext() {
        Mono<String> source = Mono.deferContextual(ctx ->
            Mono.just(ctx.getOrDefault("app.traceId", "missing"))
        );

        StepVerifier.create(
                source,
                StepVerifierOptions.create()
                    .withInitialContext(Context.of("app.traceId", "T-100"))
            )
            .expectNext("T-100")
            .verifyComplete();
    }

    @Test
    void putCreatesNewImmutableContext() {
        Context original = Context.empty();
        Context updated = original.put("app.user", "Mai");

        assertFalse(original.hasKey("app.user"));
        assertEquals("Mai", updated.get("app.user"));
    }

    @Test
    void innerContextDoesNotReplaceOuter() {
        Mono<String> source = Mono.deferContextual(ctx ->
                Mono.just(ctx.<String>get("k"))
            )
            .flatMap(value -> Mono.deferContextual(ctx ->
                Mono.just(value + ":" + ctx.<String>get("k"))
            ).contextWrite(ctx -> ctx.put("k", "inner")))
            .flatMap(value -> Mono.deferContextual(ctx ->
                Mono.just(value + ":" + ctx.<String>get("k"))
            ))
            .contextWrite(ctx -> ctx.put("k", "outer"));

        StepVerifier.create(source)
            .expectNext("outer:inner:outer")
            .verifyComplete();
    }
}
~~~

Run `gradle test` or `./gradlew test`. **All five tests are expected to PASS**. They verify subscription isolation, `contextWrite` ordering, supplying an initial Context to the subscriber via `StepVerifierOptions`, immutability, and the scope of `contextWrite` inside `flatMap`.

**Why use `StepVerifierOptions.withInitialContext`?** In a real application, the subscriber/framework may provide the initial Context. When testing a library publisher, you can simulate that **without forcing the library to call `contextWrite` on itself**. This verifies the per-subscription contract properly instead of passing Context through a static variable.

## 16. Performance and Architectural Boundaries

Context is designed for a **small number** of key/value pairs. It is not a large data store:

- Do not store a `List<Event>` with millions of elements in Context.
- Do not treat Context as mutable shared memory across requests.
- Do not use Context as a global cache, session, or database.
- Each `put` creates a new Context version; with many keys, copy-on-write can increase overhead.
- Do not use a generic key like `"id"` across multiple libraries if collisions are possible; use namespaced names or dedicated key objects.
- Do not expose tokens/secrets in logs by dumping the entire Context.
- Do not assume Context is always present in callbacks outside Reactor; when crossing boundaries into imperative libraries, use an explicit metadata propagation mechanism.

Context should only carry metadata that is **orthogonal to business payloads** and needed by upstream components during subscription execution. For mandatory, explicit business data spanning systems, prefer method parameters, records, or explicit headers/protocols.

## 17. Common Mistakes and Fixes

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| "Context belongs to a thread" | Reactor binds Context to the subscriber/subscription; threads may switch | Use `deferContextual`/`contextWrite` |
| "`Context.put` mutates the old object" | Context is immutable; `put` returns a new Context | Use the returned value, e.g. `ctx -> ctx.put(...)` |
| "`ContextView` can call `put`" | It only exposes read APIs | Write inside `contextWrite` |
| "`contextWrite` flows downward with `onNext`" | Context flows upstream during subscription, not like data signals | Place `contextWrite` downstream of the reader |
| "A downstream reader sees every `contextWrite` above it" | Scope depends on operator position | Diagram the chain and test expected values |
| "A publisher has one global Context" | Multiple subscriptions can have different Contexts | Test two subscriptions on the same source |
| "Switching schedulers erases Context" | Reactor Context does not depend on a specific thread | Read via `ContextView` inside the chain |
| "Having Context means MDC is automatically populated" | MDC uses `ThreadLocal` and needs separate propagation integration/config | Verify the Micrometer/Reactor bridge |
| "Adding an inner `contextWrite` changes the outer context" | Context inside an inner publisher is locally scoped | Pass data via emitted items if outer logic must change |
| "`get("key")` is always safe" | Missing keys throw an exception | Use `getOrDefault`/`getOrEmpty` if optional |
| "Having Context means every HTTP client sends the ID automatically" | Context exists only within the Reactor chain | Map metadata to headers/protocol intentionally |
| "Values in Context are always immutable" | Context is immutable, but values can be mutable | Store immutable values and avoid shared state |
| "Using Context to authenticate users from arbitrary headers" | Request metadata is not inherently trustworthy | Use Spring Security and trusted authentication sources |
| "A globally cached publisher has per-user Context" | Cached upstream may run once under the first subscriber's Context | Do not mix request-specific data into shared caches |

## 18. Self-Check Questions with Answers

**Q1.** Why is `ThreadLocal` poorly suited for a correlation ID in a WebFlux pipeline using `publishOn`?

**Answer:** `ThreadLocal` is bound to a thread, whereas the pipeline can switch workers. Reactor Context is bound to the subscriber/subscription and can be retrieved in Reactor operators across thread switches.

**Q2.** After `Context a = Context.empty(); a.put("k","v");`, what does `a.hasKey("k")` return?

**Answer:** `false`. `put` returns a new Context; if its return value is discarded, `a` remains an empty Context.

**Q3.** Why does `Mono.deferContextual(ctx -> Mono.just(ctx.get("k"))).contextWrite(Context.of("k","v"))` read `v`?

**Answer:** `contextWrite` is applied as subscription propagates from downstream to upstream and supplies `k=v` to `deferContextual` above it.

**Q4.** If `contextWrite` is placed upstream of a downstream reader, will the reader always see the key?

**Answer:** No. Context does not drift downstream with `onNext`; a downstream reader may not see Context written only for upstream.

**Q5.** Must two subscriptions to the same `Mono.deferContextual` with different `contextWrite` calls see the same value?

**Answer:** No. Each subscription can read its own value; that is one of the primary purposes of Context.

**Q6.** Why does `ContextView` not have `put`?

**Answer:** It is a read-only API for context-consuming code; modifying context must be an explicitly scoped transformation via `Context`/`contextWrite`.

**Q7.** Does `contextWrite(ctx -> ctx.put("k","inner"))` inside a `flatMap` inner publisher change the Context of another `flatMap` inner publisher?

**Answer:** Not under normal scoping rules. The local Context affects only that inner publisher's upstream; outer or sibling inner publishers do not receive a global mutation.

**Q8.** A `Mono` holding personal data is globally `cache()`d, and its source reads the first subscriber's Context. Are subsequent subscribers guaranteed to receive their own data?

**Answer:** No. Caching can share the first execution's result. Never mix user-specific data with a publisher/cache shared across requests.

**Q9.** In Spring WebFlux, to send a correlation ID to an external HTTP service, is `contextWrite("id")` alone enough?

**Answer:** No. Context is metadata of the Reactor subscription; you must explicitly add an HTTP header step or use a properly configured standard tracing propagation mechanism.

**Q10.** When testing a library that reads `ContextView` without writing Context itself, how do you simulate a subscriber that already has a key?

**Answer:** Use `StepVerifierOptions.create().withInitialContext(Context.of(...))` or wrap the source with `contextWrite` on the caller side, then assert the signals emitted by the publisher.

## 19. Summary and Official Documentation

**Five rules to remember:**

1. **Context is bound to the subscription/subscriber, not to a thread or a global publisher object.**
2. **`Context` is immutable with methods that produce new versions; `ContextView` is read-only.**
3. **`contextWrite` propagates from downstream to upstream at subscription time**, so read/write positions determine visibility.
4. **`deferContextual`/`transformDeferredContextual` read Context at subscription time**, even when processing steps switch workers.
5. **Context is only for small, clearly scoped metadata**; it does not replace business payloads, security mechanisms, network transport, or state stores.

Official documentation:

1. [Project Reactor Reference — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): `Context`/`ContextView`, subscription scope, `contextWrite` ordering, `flatMap`, and tracing examples.
2. [Reactor Context API](https://projectreactor.io/docs/core/release/api/reactor/util/context/Context.html): immutability contract, `put`, `delete`, `Context.of`.
3. [Reactor ContextView API](https://projectreactor.io/docs/core/release/api/reactor/util/context/ContextView.html): `get`, `getOrDefault`, `getOrEmpty`, `hasKey`.
4. [Reactor Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): `deferContextual`, `contextWrite`, `transformDeferredContextual`.
5. [Reactor Reference — Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html): `ThreadLocal`/Micrometer integration and propagation modes.
6. [Spring Framework WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html): non-blocking programming model in Spring.
