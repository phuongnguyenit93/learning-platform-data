# Isolating Context in Inner Sequences with Reactor Context

## 1. The Problem: One Stream, Multiple Inner Sequences, No Context Mixing

In a Spring WebFlux application, a request may carry a tenant ID, correlation ID, trace ID, or logging/observability metadata. Inside a service, a `Flux` may use `flatMap`, `concatMap`, or `switchIfEmpty` to create inner `Mono`/`Flux` sequences. You want those inner sequences to **read the shared request context**, while a local modification inside one inner sequence **does not mutate the context of the parent sequence or sibling inner sequences**.

That is the purpose of **isolating context in inner sequences** with Reactor Context.

Business example:

- A request belongs to tenant `shop-7` and has correlation ID `req-123`.
- A pipeline processes three order IDs.
- Each order ID has an inner sequence that queries data and sets its own `operationId`.
- All inner sequences share the request's `tenant` and `correlationId`.
- Order A's `operationId` must not bleed into order B.
- When the inner sequences finish, the parent sequence still retains its original context.

Desired model:

~~~text
                        Parent subscription's Context
                       {tenant=shop-7, trace=req-123}
                                    |
                             concatMap/flatMap
                    +---------------+---------------+
                    |               |               |
                inner A         inner B          inner C
            +operation=A     +operation=B     +operation=C
               tenant=shop-7    tenant=shop-7    tenant=shop-7
               trace=req-123    trace=req-123    trace=req-123
                    |               |               |
                    +---------------+---------------+
                                    |
                     Parent still has only tenant and trace
                    Not mutated to operation=A/B/C
~~~

**Core takeaway:** Reactor Context is bound to the **Subscriber**, not to a global thread, and it is not passed as a field on `onNext` data. Modifications via `contextWrite` create a **new Context for the upstream portion of the corresponding scope**. Therefore, a `contextWrite` placed **inside a child publisher** does not pollute the parent publisher or other child publishers.

## 2. What Is Reactor Context?

Reactor provides:

- **`reactor.util.context.Context`**: an immutable key–value store for subscription-related information. Its `put` and `delete` methods return a new Context without modifying the old one.
- **`reactor.util.context.ContextView`**: a read-only interface used to retrieve data when the pipeline is subscribed to/executed.
- **`contextWrite(...)`**: sets or transforms Context for operators upstream of itself as subscription travels from downstream to upstream.
- **`Mono.deferContextual(...)` / `Flux.deferContextual(...)`**: reads `ContextView` at subscription time to create the appropriate Publisher.
- **`transformDeferredContextual(...)`**: accesses `ContextView` alongside a publisher at subscribe time when transforming a pipeline based on Context.

You can think of Context as a small `Map<Object, Object>` for information **orthogonal** to the main business data. Unlike a mutable `HashMap`:

~~~java
Context first = Context.of("scope", "parent");
Context second = first.put("scope", "child");

// first still holds "parent"; second holds "child".
~~~

This is a short snippet inside a Java method importing `reactor.util.context.Context`. It illustrates the immutability of the **Context structure**. Note: if you store a **mutable object** (such as an `ArrayList`) as a value, mutating that object itself can still be observed by other sequences; Context immutability **does not automatically deep-copy values**.

Reactor Context is particularly well suited for correlation IDs, tenant/capability metadata, logging baggage, and per-request contextual info. It is not the place to store full request bodies, huge objects, uncontrolled secrets, or shared mutable state.

## 3. The Most Important Mechanism: Context Flows Downstream to Upstream

Many newcomers to Reactor assume Context flows with `onNext` values from top to bottom in Java code. In reality, **subscription flows backward**, and Context is tied to each Subscriber. At subscribe time, `contextWrite` supplies a new Context to the part of the pipeline **preceding it**.

Example:

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just("tenant=" + ctx.getOrDefault("tenant", "guest")))
    .contextWrite(ctx -> ctx.put("tenant", "shop-7"));

// result.block() -> "tenant=shop-7"
~~~

In the expression above, `contextWrite` appears **after** `deferContextual` in code order, yet upon subscription it makes `tenant=shop-7` visible upstream.

Diagram:

~~~text
assembly (Java source reading order):
deferContextual(read tenant) ---> contextWrite(put tenant=shop-7)

subscription/context (demand propagation from downstream):
subscribe ---> contextWrite creates Context ---> deferContextual reads Context

data signals (onNext):
deferContextual emits "tenant=shop-7" ---> downstream
~~~

Swapping positions changes the result:

~~~java
Mono<String> result = Mono.just("ok")
    .contextWrite(ctx -> ctx.put("tenant", "shop-7"))
    .flatMap(value -> Mono.deferContextual(ctx ->
        Mono.just(value + ":" + ctx.getOrDefault("tenant", "guest"))));

// result.block() -> "ok:guest"
~~~

`contextWrite` here is too **high** relative to the `flatMap` that needs to read it. It only modifies Context for its own upstream (`Mono.just("ok")`); the `flatMap` below does not see that value. Reactor did not "lose" the tenant; it is simply **outside the scope** of the write operation.

Fix:

~~~java
Mono<String> result = Mono.just("ok")
    .flatMap(value -> Mono.deferContextual(ctx ->
        Mono.just(value + ":" + ctx.getOrDefault("tenant", "guest"))))
    .contextWrite(ctx -> ctx.put("tenant", "shop-7"));

// result.block() -> "ok:shop-7"
~~~

**Practical rule:** when multiple operators need to read context, place `contextWrite` far enough **downstream** to cover the scope of all those operators.

## 4. How Does an Inner Sequence Receive the Parent Context?

An operator like `flatMap` receives an input item and produces a child Publisher. When subscribing to a child Publisher in standard Reactor fashion, it receives the **Context currently present at that operator boundary**. The child Publisher can read keys from this Context via `deferContextual`.

~~~java
Mono<String> message = Mono.just("order-42")
    .flatMap(orderId ->
        Mono.deferContextual(ctx ->
            Mono.just(orderId + " belongs to " + ctx.get("tenant"))))
    .contextWrite(Context.of("tenant", "shop-7"));

// message.block() -> "order-42 belongs to shop-7"
~~~

This means a child **can inherit** the parent's keys. However, this is not a global mutable `Map`: the child receives a Context view within **its own subscription scope**.

### What If the Child Writes the Same Key?

~~~java
Mono<String> message = Mono.just("hello")
    .flatMap(word ->
        Mono.deferContextual(ctx ->
            Mono.just(word + ":" + ctx.get("scope")))
            .contextWrite(ctx -> ctx.put("scope", "child")))
    .contextWrite(ctx -> ctx.put("scope", "parent"));

// message.block() -> "hello:child"
~~~

Inside the child publisher, its `contextWrite` is closer to the read site, so the child sees `scope=child`. **There is no upward mutation back to the parent.** The parent keeps `scope=parent`, and another child does not automatically see `scope=child`.

Distinguish these four properties:

- **Inheritance**: the child sees existing parent values unless shadowed/overridden.
- **Shadowing (local override)**: the child creates a new Context with a new value under the same key.
- **No upward propagation**: changes in the child do not modify the parent's Context.
- **No lateral propagation**: sibling B does not automatically see a Context written locally by sibling A.

This is a very useful isolation mechanism when a single request processes multiple business items.

## 5. Classic Example: Two `flatMap`s, Only the Second Has a Local Context

~~~java
Mono<String> result = Mono.just("Hello")
    .flatMap(text ->
        Mono.deferContextual(ctx ->
            Mono.just(text + " " + ctx.get("word"))))
    .flatMap(text ->
        Mono.deferContextual(ctx ->
            Mono.just(text + " " + ctx.get("word")))
            .contextWrite(ctx -> ctx.put("word", "Child")))
    .contextWrite(ctx -> ctx.put("word", "Parent"));

// result.block() -> "Hello Parent Child"
~~~

**Step-by-step explanation:**

1. The final `contextWrite` creates a parent Context with `word=Parent` for the pipeline above it.
2. In the first `flatMap`, the inner Publisher reads `word` from the parent Context: producing `Hello Parent`.
3. In the second `flatMap`, the inner Publisher has its own `contextWrite` setting `word=Child` **internally for that inner sequence**: producing `Hello Parent Child`.
4. The second inner sequence's local Context **does not go back and alter the first inner sequence**.
5. The result is neither `Hello Child Child` nor `Hello Parent Parent`.

This is the classic example explained in the Reactor Core Reference Guide. It demonstrates that Context **does not ride alongside individual `onNext` values**; local changes in an inner sequence do not alter the Context of the entire chain.

## 6. Isolating Multiple Children with `concatMap`

Suppose there are two orders A and B, each with its own `operationId`. We use `concatMap` so the example's output order is deterministic:

~~~java
Flux<String> orders = Flux.just("A", "B")
    .concatMap(orderId ->
        Mono.deferContextual(ctx -> Mono.just(
            orderId +
            " tenant=" + ctx.get("tenant") +
            " operation=" + ctx.get("operation")))
        .contextWrite(ctx -> ctx.put("operation", "read-" + orderId)))
    .contextWrite(ctx -> ctx.put("tenant", "shop-7")
                            .put("operation", "parent"));

// When subscribed, emits:
// A tenant=shop-7 operation=read-A
// B tenant=shop-7 operation=read-B
~~~

Both children read `tenant=shop-7`, yet each child has a different `operation`. Even with the same source Flux instance, the value `read-A` **does not leak to child B** and does not alter the parent.

If using `flatMap` with asynchronous children, **result ordering may vary** due to concurrency; Context isolation still follows subscription scope and does not depend on result ordering. If sequential processing in source order is required, choose `concatMap`; if concurrency is needed while keeping source order on output, consider `flatMapSequential`. **Do not use `concatMap` merely to "fix Context leaks"**; the scoping mechanism does not require sequential execution.

## 7. Two Independent Subscriptions from the Same `Mono`

Reactor Context is bound to the **subscription**, so two requests can share the exact same pipeline definition while carrying two different Contexts:

~~~java
Mono<String> readTenant = Mono.deferContextual(ctx ->
    Mono.just(ctx.get("tenant")));

String first = readTenant
    .contextWrite(Context.of("tenant", "tenant-A"))
    .block();

String second = readTenant
    .contextWrite(Context.of("tenant", "tenant-B"))
    .block();

// first = "tenant-A"
// second = "tenant-B"
~~~

The two `block()` calls create two subscriptions without reassigning any static field. `tenant-A` is not a global default retained for the next subscription.

### Isolation Does Not Depend on Same or Different Threads

Two reactive pipelines can run on the same event-loop thread at different times, or hop across threads when using `publishOn`, `subscribeOn`, or `Mono.delay`'s scheduler. Reactor Context is attached to subscribers in the pipeline rather than stored in `ThreadLocal`. Consequently, a pipeline using Context properly does not rely on an invariant thread to identify a tenant.

However, this **does not guarantee that arbitrary callback libraries know how to read Reactor Context**. Reactor Context must be read via Reactor APIs or passed explicitly at boundaries.

## 8. Compilable and Runnable Java 17+ Full Demo

The example below demonstrates four independent observations:

1. Two subscriptions see different tenants.
2. Children have their own scopes and the parent remains unchanged before and after the children.
3. The order of `contextWrite` determines which part of the pipeline sees a key.
4. Context remains readable in reactive work whose scheduler switches threads.

### Structure and Dependencies

Requires **JDK 17+**, **Maven 3.9+**.

~~~text
reactor-context-isolation/
  pom.xml
  src/main/java/example/ContextIsolationDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-context-isolation</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.17</version>
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

**src/main/java/example/ContextIsolationDemo.java**

~~~java
package example;

import java.time.Duration;
import java.util.List;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

public final class ContextIsolationDemo {
    private static final String TENANT = "tenant";
    private static final String SCOPE = "scope";

    public static void main(String[] args) {
        // 1) Same Mono, two subscriptions with different Contexts.
        Mono<String> probe = Mono.deferContextual(ctx ->
            Mono.just(ctx.<String>get(TENANT)));

        System.out.println("first=" +
            probe.contextWrite(Context.of(TENANT, "tenant-A")).block());
        System.out.println("second=" +
            probe.contextWrite(Context.of(TENANT, "tenant-B")).block());

        // 2) Parent has scope=root; each child shadows its own scope.
        Mono<String> parentProbe = Mono.deferContextual(ctx ->
            Mono.just("parent:" + ctx.get(SCOPE)));

        Flux<String> children = Flux.just("A", "B")
            .concatMap(id ->
                Mono.deferContextual(ctx ->
                    Mono.just(
                        "child-" + id +
                        ":tenant=" + ctx.get(TENANT) +
                        ",scope=" + ctx.get(SCOPE)))
                .contextWrite(ctx -> ctx.put(SCOPE, "local-" + id)));

        List<String> scopes = Flux.concat(
                parentProbe.flux(),
                children,
                parentProbe.flux())
            .contextWrite(Context.of(
                TENANT, "shop-7",
                SCOPE, "root"))
            .collectList()
            .block();

        System.out.println("scopes=" + scopes);

        // 3) contextWrite only affects its own upstream.
        Mono<String> tooHigh = Mono.just("data")
            .contextWrite(ctx -> ctx.put(TENANT, "hidden"))
            .flatMap(value ->
                Mono.deferContextual(ctx ->
                    Mono.just("downstream=" +
                        ctx.getOrDefault(TENANT, "none"))));

        Mono<String> correct = Mono.just("data")
            .flatMap(value ->
                Mono.deferContextual(ctx ->
                    Mono.just("upstream=" +
                        ctx.getOrDefault(TENANT, "none"))))
            .contextWrite(ctx -> ctx.put(TENANT, "visible"));

        System.out.println(tooHigh.block());
        System.out.println(correct.block());

        // 4) ContextView read at subscription then used in async work.
        Mono<String> asynchronous = Mono.deferContextual(ctx ->
                Mono.delay(Duration.ofMillis(5))
                    .map(tick -> "async=" + ctx.<String>get(TENANT)))
            .contextWrite(Context.of(TENANT, "across-thread"));

        System.out.println(asynchronous.block());

        // 5) A contextWrite in one inner does not alter another inner.
        Mono<String> nested = Mono.just("Hello")
            .flatMap(s -> Mono.deferContextual(ctx ->
                Mono.just(s + " " + ctx.get("word"))))
            .flatMap(s ->
                Mono.deferContextual(ctx ->
                    Mono.just(s + " " + ctx.get("word")))
                .contextWrite(ctx -> ctx.put("word", "Child")))
            .contextWrite(ctx -> ctx.put("word", "Parent"));

        System.out.println(nested.block());
    }
}
~~~

### Running the Program

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.ContextIsolationDemo
~~~

**Lines printed by the program** (excluding Maven/JVM messages if added by your environment):

~~~text
first=tenant-A
second=tenant-B
scopes=[parent:root, child-A:tenant=shop-7,scope=local-A, child-B:tenant=shop-7,scope=local-B, parent:root]
downstream=none
upstream=visible
async=across-thread
Hello Parent Child
~~~

Output explanation:

- **first/second**: same `probe` source, yet Context is supplied independently for the two subscriptions.
- **scopes**: both before and after the children, the parent still has `scope=root`; children A/B read the shared tenant while shadowing different scopes.
- **downstream=none**: `contextWrite` is too high, failing to cover the read after `flatMap`.
- **upstream=visible**: moving `contextWrite` below `flatMap` lets the read see the key.
- **async=across-thread**: context is obtained inside `deferContextual` and used when `Mono.delay` emits on a scheduler; it does not rely on a `ThreadLocal` from the original thread.
- **Hello Parent Child**: overriding in the second inner sequence does not alter the first inner sequence's result.

The `block()` calls are used solely at the **CLI program boundary to observe results**. In a WebFlux controller, you should normally **return `Mono`/`Flux`** for the framework to subscribe to, rather than calling `block()` on a Netty event-loop thread.

## 9. `contextWrite` in an Inner Sequence vs. `contextWrite` in the Parent Pipeline

Compare these two patterns:

**Pattern A — Shared Context for the entire chain:**

~~~java
Flux<String> result = Flux.just("x", "y")
    .flatMap(id ->
        Mono.deferContextual(ctx ->
            Mono.just(id + ":" + ctx.get("traceId"))))
    .contextWrite(ctx -> ctx.put("traceId", "request-1"));
~~~

Both inner Publishers created via `flatMap` can read `traceId=request-1`. This `contextWrite` sits downstream of the entire `flatMap` operator.

**Pattern B — Local Context per inner sequence:**

~~~java
Flux<String> result = Flux.just("x", "y")
    .flatMap(id ->
        Mono.deferContextual(ctx ->
            Mono.just(id + ":" + ctx.get("scope")))
        .contextWrite(ctx -> ctx.put("scope", "local-" + id)))
    .contextWrite(ctx -> ctx.put("scope", "parent"));
~~~

Each inner sequence sees its own scope; the parent is not mutated. The emitted items are the two strings `x:local-x` and `y:local-y`, though **emission order may vary** because `flatMap` is used. If deterministic ordering is needed for tests, use `concatMap`.

**Key distinction:** Context is **written per Subscriber scope**, not passed by assigning the variable `id`. Both patterns use a parent Publisher, but the placement of `contextWrite` determines the write scope.

## 10. Why Can't You "Set Context" Inside `map` and Expect It to Spread?

A common misconception is creating a new Context inside `map`, like this:

~~~java
Mono<String> wrong = Mono.just("x")
    .map(value -> {
        Context ignored = Context.of("scope", "new");
        return value;
    })
    .flatMap(value ->
        Mono.deferContextual(ctx ->
            Mono.just(ctx.getOrDefault("scope", "missing"))));
~~~

This snippet merely **constructs a Context object inside a lambda** and discards it. It does not attach that Context to any Subscriber. Thus `deferContextual` below still reads `missing` unless `scope` comes from elsewhere.

Similarly, even if you have a variable `Context old` and call `Context newer = old.put("scope","new")`, there is no automatic mechanism that injects `newer` into the running subscription. `put` creates a new object; **only pipeline structure via `contextWrite` and proper propagation APIs determines where Context is visible**.

When you need context that depends on the item currently being processed, move that dependent value into an **inner Publisher** and attach a local `contextWrite` to that inner Publisher:

~~~java
Flux<String> result = Flux.just("A", "B")
    .concatMap(id ->
        Mono.deferContextual(ctx ->
            Mono.just(ctx.get("scope") + ":" + id))
        .contextWrite(ctx -> ctx.put("scope", "op-" + id)));
~~~

This is the primary pattern for per-item context isolation.

## 11. Avoid Manual `subscribe()` Inside Inner Sequences

A common anti-pattern is starting an **independent** subscription inside `doOnNext` or a callback:

~~~java
Flux.just("A")
    .doOnNext(id -> {
        Mono.deferContextual(ctx ->
                Mono.just(ctx.getOrDefault("traceId", "missing")))
            .subscribe(System.out::println); // independent subscription
    })
    .contextWrite(ctx -> ctx.put("traceId", "request-1"))
    .subscribe();
~~~

This snippet calls `subscribe()` manually inside a callback; because that starts a new subscription, it is **not automatically attached** to the parent subscription's Context. The inner sequence may print `missing` instead of `request-1`. Beyond losing Context, this pattern breaks propagation of **errors, cancellation, backpressure, and completion**; the framework no longer owns the inner work.

The proper composition:

~~~java
Flux<String> result = Flux.just("A")
    .flatMap(id ->
        Mono.deferContextual(ctx ->
            Mono.just(id + ":" + ctx.get("traceId"))))
    .contextWrite(ctx -> ctx.put("traceId", "request-1"));

// Upon subscribe: A:request-1
~~~

`flatMap` subscribes to the inner Publisher **as part of the pipeline**, so signals and Context compose according to Reactor's contract.

Do not take a `Mono` or `Flux` inside an async callback and immediately call `subscribe()` just to "kick off" work. Return that Publisher to an appropriate operator such as `flatMap`, `concatMap`, or `then`.

## 12. `ContextView`: Reading the Right Key and Managing Collisions

Example of reading a required key:

~~~java
Mono<String> value = Mono.deferContextual(ctx ->
    Mono.just(ctx.<String>get("tenantId")));
~~~

If this key does not exist, `get` throws an exception when the source is subscribed to. For optional keys, use `getOrDefault` or `getOrEmpty`:

~~~java
Mono<String> value = Mono.deferContextual(ctx ->
    Mono.just(ctx.getOrDefault("traceId", "not-provided")));
~~~

Points to keep in mind:

- Keys and values are typed as `Object`, so there is **no blanket type safety** across all key/value pairs.
- You can use dedicated key types (typed/unique key objects) or clearly namespaced names to avoid collisions between libraries.
- If two components both use `"tenant"` with different meanings, one `contextWrite` can unintentionally shadow the other component's value.
- For required keys, fail meaningfully and test the missing-key case. For optional keys, use safe defaults.
- Do not put `null` as a key or value; Context cannot hold null entries.
- Do not dump the entire Context into logs or HTTP responses; it may contain internal observability or security data.

Example using a unique key object to limit collisions:

~~~java
static final Object TENANT_KEY = new Object();

Mono<String> value = Mono.deferContextual(ctx ->
        Mono.just(ctx.<String>get(TENANT_KEY)))
    .contextWrite(ctx -> ctx.put(TENANT_KEY, "shop-7"));
~~~

This is an **illustrative snippet inside a Java class**, not standalone code; `TENANT_KEY` must be defined at class level. Both writer and reader must use **the same key object**.

## 13. Do Not Confuse Immutable Context with Isolating Mutable Objects

The biggest hazard is placing a shareable mutable object into Context:

~~~java
List<String> shared = new ArrayList<>();
Context base = Context.of("audit", shared);

Context childA = base.put("scope", "A");
Context childB = base.put("scope", "B");

// Avoid doing this if the same List is used by both A and B:
((List<String>) childA.get("audit")).add("from-A");
System.out.println(childB.<List<String>>get("audit"));
// May print [from-A] because both Contexts hold the same shared reference.
~~~

This is an **illustrative snippet** requiring imports for `java.util.List`, `ArrayList`, and `Context`; the sample cast is not recommended style. Although `childA` and `childB` are distinct Contexts, the same `audit` key points to **one List**. Therefore, **structural Context isolation does not automatically provide deep isolation of value objects**.

Best practices:

- Use immutable values such as `String`, IDs, enums, or immutable Java records.
- Choose stable context keys and keep the number of keys small.
- Do not share mutable containers across requests or inner Publishers without explicit synchronization and lifecycle design.
- If you truly need per-child state, create **separate state per child** via `Mono.defer`/`Flux.defer` and keep that reference scoped strictly to that child.
- If the data is part of item-processing logic, prefer passing it inside business values/records rather than overusing Reactor Context.

Example of a suitable immutable value:

~~~java
record RequestMeta(String tenantId, String correlationId) {}

Mono<String> value = Mono.deferContextual(ctx -> {
    RequestMeta meta = ctx.get("requestMeta");
    return Mono.just(meta.tenantId() + "/" + meta.correlationId());
});
~~~

This is a **snippet inside a Java method or class**, requiring Java 17+ and a Context holding `RequestMeta`. A record makes the value clear, though its fields themselves must be immutable types if deep isolation is needed.

## 14. Context and Schedulers: Why `ThreadLocal` Cannot Substitute Directly

In traditional servlets, one request is typically bound to one thread across many steps, so you can store a request ID in `ThreadLocal` or MDC. In WebFlux, a single Netty thread can serve multiple subscriptions in turn; a pipeline can also hop to other schedulers.

~~~text
Subscription A: event-loop-1 ---> parallel-2 ---> event-loop-1
Subscription B: event-loop-1 ---> boundedElastic-3
Subscription C: event-loop-1 ---> parallel-1

ThreadLocal is only per-Thread data.
Reactor Context is logical data per Subscriber/subscription.
~~~

Do not assume `ThreadLocal.get()` inside a callback after `delayElement`, `publishOn`, or async I/O will read the `ThreadLocal` of a previous callback. And never assume that because two requests share an event-loop thread, they are allowed to share the same tenant.

Reactor has built-in **context-propagation** support via Micrometer Context Propagation, `contextCapture`, and (when configured) `Hooks.enableAutomaticContextPropagation()`. These mechanisms help interoperate with libraries that use `ThreadLocal`/MDC, but they **depend on dependencies, registry, accessors, and configuration mode**. Do not assume `ThreadLocal` is always bridged in every application.

For reading tenant/trace inside a Reactor pipeline, the clearest approach is usually:

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
    client.fetch(ctx.<String>get("tenantId")));
~~~

This illustrative snippet assumes `client.fetch` returns `Mono<String>` and is designed to be non-blocking. `deferContextual` reads the subscription's tenant and **passes it explicitly** into the client's API. No `ThreadLocal` is needed.

## 15. When Do You Need `transformDeferredContextual`?

If you want to transform a `Flux` based on the current Context without wrapping each child in `deferContextual`, you can use `transformDeferredContextual`:

~~~java
Flux<String> labels = Flux.just("A", "B")
    .transformDeferredContextual((source, ctx) ->
        source.map(id ->
            ctx.getOrDefault("tenant", "guest") + ":" + id))
    .contextWrite(ctx -> ctx.put("tenant", "shop-7"));

// Upon subscribe: "shop-7:A", "shop-7:B"
~~~

This is a Java expression example importing `Flux`, not a standalone class. Unlike ordinary `map`, `transformDeferredContextual` can access `ContextView` at subscription time. It is useful when a transformation needs to read metadata for the whole subscription.

Distinguish among:

- `Mono.deferContextual` / `Flux.deferContextual`: creates a Context-dependent source.
- `transformDeferredContextual`: transforms an existing publisher with `ContextView` at subscribe time.
- `contextWrite`: writes/merges Context for upstream.
- `flatMap` and `concatMap`: reactively compose created child Publishers.

You do not need `transformDeferredContextual` in every service; choose the operator that makes the code clearest.

## 16. Applying in Spring WebFlux: Tenant and Correlation ID

At the HTTP boundary, a `WebFilter` can determine the tenant from a **trusted source** such as an authenticated principal or internal authentication mechanism, then place that value into the Reactor Context of the request-processing pipeline.

**Architectural illustration** (requires application components and imports):

~~~java
@Component
class TenantContextFilter implements WebFilter {
    static final String TENANT_KEY = "app.tenantId";

    private final TrustedTenantResolver tenantResolver;

    TenantContextFilter(TrustedTenantResolver tenantResolver) {
        this.tenantResolver = tenantResolver;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        return tenantResolver.resolve(exchange)
            .flatMap(tenantId ->
                chain.filter(exchange)
                    .contextWrite(ctx -> ctx.put(TENANT_KEY, tenantId)));
    }
}
~~~

This is an **integration pattern**, not standalone: you must define `TrustedTenantResolver` with `Mono<String> resolve(ServerWebExchange)` and import `@Component`, `WebFilter`, `ServerWebExchange`, `WebFilterChain`, and `Mono`. Do not take the tenant from an arbitrary client-spoofable header if it serves as an access-control basis. Depending on your security mechanism, ensure compatibility with how Spring Security manages Reactor Context and filter ordering.

In a service:

~~~java
Mono<Order> loadOrder(String orderId) {
    return Mono.deferContextual(ctx -> {
        String tenant = ctx.get(TenantContextFilter.TENANT_KEY);
        return orderRepository.findByTenantAndId(tenant, orderId);
    });
}
~~~

This example assumes `Order` and `orderRepository` exist. For a request processing multiple orders, you can add local metadata per inner sequence:

~~~java
Flux<Order> loadOrders(Flux<String> orderIds) {
    return orderIds.flatMap(orderId ->
        loadOrder(orderId)
            .contextWrite(ctx ->
                ctx.put("app.operationId", "load:" + orderId)));
}
~~~

Each inner sequence gets its own operation ID. Yet it cannot alter the tenant of the parent request or siblings; at the same time, the repository must always **use the tenant from a trusted source to filter data**, never treating mere presence of Context as sufficient access control.

**Do not transmit the raw Context over the network.** If propagation to a downstream HTTP service is needed, extract only permitted fields (such as trace/correlation IDs) and attach them to headers via a `WebClient` filter/client adapter per contract, with data and security controls.

## 17. What to Know When Using `cache`, `share`, and Hot Sources

Per-subscriber isolation **does not mean** a pipeline with `cache`/`share` always executes the entire source separately for every subscriber.

Example:

~~~java
Mono<String> once = Mono.deferContextual(ctx ->
        Mono.just(ctx.<String>get("tenant")))
    .cache();
~~~

If this `once` instance is shared across multiple requests with different tenants, `cache()` can cause the source to be subscribed to and computed once for one subscription and replayed to subsequent subscribers. That poses a risk of **cross-tenant data leakage** if tenant-dependent content is cached without keying by tenant.

Never assume that every hot source, `share`, or `cache` will create a fresh upstream Context per subscriber. Actual subscription scope, sharing point, and cache operator behavior matter greatly.

Mitigations:

- Keep Context-sensitive computations **within the proper subscription scope**; do not cache request-specific results application-wide.
- If caching is needed, design **cache keys that include tenant and required access-control parameters**, along with eviction/expiration policies.
- For hot sources, determine the Context of the **actual upstream subscription**; do not assume downstream subscribers' Contexts are aggregated.
- Test with multiple concurrent tenants/subscribers rather than testing only a single request.
- Never store secrets or user data in shared mutable context values.

## 18. Testing Isolation with `StepVerifier`

The `reactor-test` library provides `StepVerifier`; to test Reactor Context, add the test dependency matching your `reactor-core` version:

~~~xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <version>3.6.17</version>
    <scope>test</scope>
</dependency>
~~~

Test example, to be placed inside a test method importing `reactor.test.StepVerifier`, `Flux`, `Mono`, and `Context`:

~~~java
Flux<String> sequence = Flux.just("A", "B")
    .concatMap(id ->
        Mono.deferContextual(ctx ->
            Mono.just(id + ":" + ctx.<String>get("scope")))
        .contextWrite(ctx -> ctx.put("scope", "inner-" + id)))
    .contextWrite(Context.of("scope", "parent"));

StepVerifier.create(sequence)
    .expectNext("A:inner-A", "B:inner-B")
    .verifyComplete();
~~~

You can use `StepVerifierOptions.withInitialContext(...)` to supply context directly at the subscriber in a test:

~~~java
StepVerifier.create(
        Mono.deferContextual(ctx ->
            Mono.just(ctx.<String>get("tenant"))),
        StepVerifierOptions.create()
            .withInitialContext(Context.of("tenant", "tenant-A")))
    .expectNext("tenant-A")
    .verifyComplete();
~~~

This is also an illustrative test snippet requiring `reactor.test.StepVerifierOptions`. Using initial Context in tests verifies the behavior of a library/service when the consumer provides the Context, without always having to put `contextWrite` into production pipelines.

Tests should cover:

1. Same Publisher, two subscribers with different Contexts do not see each other's data.
2. When a child overrides a key, the parent and siblings keep their old values.
3. A child that does not override a key inherits the key from its parent.
4. When a required key is missing, the publisher fails predictably; optional keys fall back to defaults.
5. Multiple children running concurrently with `flatMap` do not mix operation IDs.
6. Scheduler switches do not accidentally make logic depend on `ThreadLocal`.
7. `cache`/`share` scenarios do not risk replaying results for another tenant.
8. Sensitive data is not emitted in logs or responses.

When testing async `flatMap`, do not assert order with `expectNext(A, B)` if order can vary; choose `concatMap` for deterministic ordering in examples or assert the collection appropriately.

## 19. Common Mistakes and Fixes

| Mistake | Why It Is Wrong | Right Approach |
| --- | --- | --- |
| Treating Reactor Context like a global mutable `HashMap` | Context is bound to the Subscriber; `put` returns a new instance | Use `contextWrite` within the required pipeline scope |
| Assuming `contextWrite` affects every operator below it | Writing Context affects operators **upstream** of its position | Place `contextWrite` downstream of the reads |
| Calling `contextWrite` in an inner sequence and expecting the parent to change | Inner only alters the child subscription's Context | Write in the parent if you want to share across branches |
| Writing `operationId` on the parent for all items | All children will see one ID with no per-item isolation | Place `contextWrite` on the child Publisher created by `flatMap`/`concatMap` |
| Calling `subscribe()` manually inside a callback | New subscription does not inherit parent Context; loses lifecycle | Return the child Publisher and compose via `flatMap`/`concatMap` |
| Using `ThreadLocal` as the source of truth for tenant in async pipelines | Threads can switch or serve multiple subscriptions | Use Reactor Context or pass explicit parameters |
| Putting a shared mutable `List` in Context | An immutable map does not make the `List` immutable | Use immutable values or create separate state per child |
| Overwriting same-named keys across libraries | Unintended collisions and shadowing | Use namespaced/typed keys and clear contracts |
| Using `get(key)` when the key may be absent | Missing key causes a runtime error | Use `getOrDefault`/`getOrEmpty` or explicit validation |
| Using `cache()` on tenant-dependent results | Cache can replay data out of scope | Key cache by tenant properly or avoid sharing |
| Assuming `flatMap` always preserves A, B, C order | `flatMap` can run inner sequences concurrently, changing order | Use `concatMap` when order is needed; separate concurrency from isolation |
| Dumping the whole Context into headers/logs | Can expose data not meant for clients | Forward only allowed keys with proper redaction |
| Using Context for authorization without validating identity | Keys could be forged or mis-supplied at boundaries | Obtain tenant/identity from trusted sources and enforce authorization |
| Assuming every library outside Reactor sees Context automatically | Non-Reactor callbacks/libraries do not read Context on their own | Read and pass explicitly or use standard bridging |

## 20. Self-Check Exercises

**Q1.** When calling `contextWrite(ctx -> ctx.put("scope", "child"))` inside a `flatMap` Publisher, does the parent Publisher switch to `scope=child`?

**No.** The new Context is scoped upstream of that child Publisher. The parent and siblings are not updated automatically.

**Q2.** If the same `Mono.deferContextual` is subscribed to twice with tenant A and tenant B, which tenant must it return?

**Each run returns the tenant matching that subscription's Context**, unless the pipeline is altered by `cache`/`share` or a source with different semantics.

**Q3.** Why can placing `contextWrite` before `flatMap` prevent the inner sequence from reading the key?

Because Context propagates from downstream to upstream. `contextWrite` only modifies the Context of operators **above it**, without necessarily affecting the `flatMap` placed after it.

**Q4.** Why shouldn't you use `doOnNext(id -> mono.subscribe())` to spawn business child work?

Because that `subscribe()` creates an **independent subscription** that does not automatically inherit the parent's Context/lifecycle, breaking error, cancellation, and backpressure composition.

**Q5.** Does an immutable Context guarantee an `ArrayList` value cannot be mutated jointly by children?

**No.** Two Contexts can point to the same mutable `List`. Use immutable values or separate state.

**Q6.** Can a WebFlux application read the tenant from a fixed `ThreadLocal` after `publishOn`?

**Do not assume** so. Use Reactor Context or configure appropriate context propagation and test in a real environment.

**Q7.** When you want children A/B to share a common tenant while having separate operation IDs, where do you place the two keys?

Place **tenant at the request/parent scope**, and **operation ID on the inner Publisher** inside `flatMap`/`concatMap`.

**Q8.** You need to process multiple children concurrently without mixing operation IDs. Is `concatMap` mandatory?

**No.** Per-child Publisher Context isolation still applies with `flatMap`. `concatMap` is only chosen when ordering and sequential execution are required.

**Q9.** Does Context automatically become HTTP headers when calling `WebClient`?

**No.** You need an adapter/filter that reads permitted keys and attaches them to requests per contract, watching out for sensitive data.

**Q10.** Why can caching a `Mono` that reads tenant from Context be dangerous?

Because the source may execute for one subscription and replay the same result to multiple subscribers; if the result is tenant-dependent, this creates a cross-request data mixing risk.

## 21. References

- [Project Reactor Reference Guide — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): Context definition, propagation direction, `contextWrite`, `deferContextual`, and `flatMap` isolation examples.
- [Reactor Core API — Context](https://projectreactor.io/docs/core/release/api/reactor/util/context/Context.html): immutability, `put`, `delete`, and `putAll` methods.
- [Reactor Core API — ContextView](https://projectreactor.io/docs/core/release/api/reactor/util/context/ContextView.html): reading with `get`, `getOrDefault`, `getOrEmpty`, and `hasKey`.
- [Reactor Core Reference Guide — Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html): distinguishing Reactor Context from `ThreadLocal` and propagation modes.
- [Reactor Core API — Mono](https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/Mono.html) and [Flux](https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/Flux.html): `deferContextual`, `contextWrite`, and operators creating inner Publishers.
- [Reactor Test API — StepVerifierOptions](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifierOptions.html): configuring initial Context during tests.

**Takeaway:** Reactor Context is an **immutable metadata store bound to the Subscriber**, propagated along the **subscription direction from downstream to upstream**. `contextWrite` creates a new Context within the scope where it is placed; when placed **inside a child Publisher**, it does not automatically alter the parent's or siblings' Context. `deferContextual` lets you read metadata at subscription time. Use Context to carry shared tenant/trace metadata, set per-inner metadata via local `contextWrite`, avoid manual `subscribe()`, avoid shared mutable state, and always check `cache`/`share`, scheduler, and HTTP security boundaries.