# Writing Context with `contextWrite` in Project Reactor

## 1. Purpose and Use Cases

In Spring Framework Reactive and Spring WebFlux, `Mono<T>` and `Flux<T>` sequences can run across multiple operators, multiple threads, and multiple library layers. Sometimes multiple layers need a piece of technical information attached to each request — such as a **request ID**, correlation ID, authenticated tenant ID, or preferred locale — without adding those parameters to every data-processing method.

**Reactor Context** is a mechanism for storing key–value data **bound to a subscription**, independent of the contents of `onNext` signals. To **write, add, or modify Context values** for the upstream portion of a pipeline, use the `contextWrite` operator.

After this lesson, you should be able to:

1. Create and write `Context` using `contextWrite(ContextView)` or `contextWrite(Function<Context, Context>)`.
2. Explain why Context flows **from downstream to upstream at subscription time**, opposite to the direction of `onNext` data.
3. Understand how the placement of `contextWrite` determines which operators can read a key.
4. Apply the rules for **immutability**, duplicate keys, overwriting, deleting keys, and per-subscriber isolation.
5. Read Context at the right time using `Mono.deferContextual`, `Flux.deferContextual`, or `transformDeferredContextual` to verify writes.
6. Avoid confusing Context with Java `ThreadLocal`, business data flowing through `map`/`flatMap`, or global variables.
7. Use Context deliberately in Spring WebFlux without creating separate subscriptions outside the request lifecycle.

### Example Problem

~~~java
Mono<String> greeting = Mono.deferContextual(ctx ->
    Mono.just("Hello " + ctx.<String>get("name"))
).contextWrite(ctx -> ctx.put("name", "Linh"));
~~~

When `greeting` is subscribed to and completes, it emits `Hello Linh`. Even though `contextWrite` appears **after** `deferContextual` in code, the reader above still receives `name=Linh`. The reason is that **Context is supplied along the subscription direction**, not the data direction.

## 2. Distinguishing Publisher Data, Context, and ThreadLocal

Suppose an HTTP request needs to return an `Order`. The `Order` object is the Publisher's **business data**, whereas `traceId` is technical metadata used to log steps belonging to the same request.

| Mechanism | Bound to | How to access | Limitations / Meaning |
| --- | --- | --- | --- |
| `Mono<Order>` / `Flux<Order>` | `onNext` data signals | `map`, `flatMap`, `subscribe` | Represents the data the application processes |
| `Context` / `ContextView` | A Reactor subscription | `contextWrite` to write, `deferContextual` to read | Carries subscription-specific metadata |
| `ThreadLocal<T>` | A specific Java thread | `get`/`set` | Does not automatically follow data when `publishOn`/`subscribeOn` switches threads |
| `static` / global variables | Entire process | Direct access | Easily leaks or overwrites data across concurrent requests |

A single `Mono` instance can be subscribed to multiple times; each subscriber can carry a **different Context** even when sharing the same Publisher.

~~~text
                       same Publisher
                    Mono.deferContextual(...)
                      /            \
             subscription A      subscription B
             Context: rid=A      Context: rid=B
               reads rid=A         reads rid=B
~~~

This is especially important in WebFlux because many HTTP requests share the same singleton service. Do not store per-user request IDs in a mutable field of a singleton.

**Context does not replace business data.** If a `save(order)` function needs the `Order` object itself to do its work, pass it through `flatMap`/`map` or an explicit contract parameter. Context should hold *orthogonal* metadata such as trace/correlation data, not an arbitrary application-wide data store.

## 3. Core APIs: `Context` and `ContextView`

Reactor provides:

- `reactor.util.context.Context`: key–value interface that cannot be mutated in place. It provides `put`, `putAll`, and `delete`, where **each operation creates a new Context**.
- `reactor.util.context.ContextView`: read-only interface. Readers such as `Mono.deferContextual` receive a `ContextView` rather than granting arbitrary write access.

Keys and values are typed as `Object`. Key names should be clear and unlikely to collide; for typed access, you can use a dedicated key object/constant. **Do not pass `null` as a key or value** into Context.

Common Context construction examples:

~~~java
Context empty = Context.empty();

Context one = Context.of("requestId", "REQ-1");

Context two = Context.of(
    "requestId", "REQ-1",
    "tenantId", "tenant-A"
);

Context edited = two.put("locale", "vi-VN");
Context withoutTenant = edited.delete("tenantId");
~~~

`two` **does not change** after `put`; `edited` likewise does not change after `delete`. To keep the result, you must use the returned value.

~~~java
Context c = Context.of("mode", "old");
c.put("mode", "new"); // Not reassigned!
System.out.println(c.<String>get("mode")); // old

c = c.put("mode", "new");
System.out.println(c.<String>get("mode")); // new
~~~

### Reading Values and Handling Missing Keys

~~~java
Mono<String> read = Mono.deferContextual(ctx -> {
    boolean present = ctx.hasKey("requestId");
    String requestId = ctx.getOrDefault("requestId", "unknown");
    return Mono.just(present + ":" + requestId);
});
~~~

- `ctx.get(key)`: retrieves the value; may throw `NoSuchElementException` if the key does not exist. Use when the **contract** requires the key to be present.
- `ctx.getOrDefault(key, fallback)`: retrieves the value or fallback; suitable for optional metadata.
- `ctx.getOrEmpty(key)`: returns `Optional<T>`.
- `ctx.hasKey(key)`: checks existence.
- `ctx.stream()` or `size()` can be used for diagnostics, but you should not blindly print the entire Context because it may contain sensitive metadata.

Note: **immutability at the Context structure level** does not make value objects immutable themselves. If you put a mutable `HashMap` into Context, two parts referencing that map can still mutate its state. Prefer small, immutable values such as IDs, enums, records, or read-only structures.

## 4. Two Overloads of `contextWrite`

Both `Mono` and `Flux` support writing Context at a `contextWrite` boundary.

### 4.1. `contextWrite(ContextView)`: Adding Known Key–Value Pairs

~~~java
Mono<String> requestId = Mono.deferContextual(ctx ->
        Mono.just(ctx.<String>get("requestId")))
    .contextWrite(Context.of("requestId", "REQ-42"));
~~~

`Context.of(...)` is a `ContextView`, so this overload adds known key–value pairs for the upstream portion.

Exact semantics: `contextWrite(ContextView additional)` **merges** pairs from `additional` with the downstream subscriber's Context, producing a new Context for upstream. Keys in the added Context can **overwrite matching downstream keys** within the upstream scope, rather than discarding all other keys by default.

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just(ctx.<String>get("requestId") + "/"
                 + ctx.<String>get("locale")))
    .contextWrite(Context.of("locale", "vi"))
    .contextWrite(Context.of("requestId", "REQ-42"));
~~~

In this example, downstream provides `requestId`, and the boundary closer to the source adds `locale`; the reader above sees both. If each subscription needs a different request ID, you can create a new Publisher with the corresponding `Context.of(...)` or use the `Function` overload to compute metadata based on the downstream Context.

### 4.2. `contextWrite(Function<Context, Context>)`: Modifying Based on Downstream Context

~~~java
Mono<String> message = Mono.deferContextual(ctx ->
        Mono.just("trace=" + ctx.<String>get("traceId")))
    .contextWrite(ctx -> ctx.put("traceId", "T-123"));
~~~

The lambda receives the downstream Context (as an object not mutated in place) and **must return a new Context** for upstream. Because `put` returns a new Context, `ctx -> ctx.put(...)` is the right pattern.

Writing multiple keys:

~~~java
.contextWrite(ctx ->
    ctx.put("requestId", "R-1")
       .put("locale", "vi-VN")
       .put("channel", "api"))
~~~

Deleting a key intentionally:

~~~java
.contextWrite(ctx -> ctx.delete("temporaryFlag"))
~~~

Conditionally transforming from the downstream context:

~~~java
.contextWrite(ctx -> {
    String current = ctx.getOrDefault("traceId", "not-set");
    return ctx.put("traceId", current + "-child");
})
~~~

Key point: **do not return `null`, and do not drop other keys unintentionally**. Because the function receives the downstream context, doing `ctx -> Context.of("traceId", "R")` discards other keys already in the Context. Usually, use `ctx.put(...)`/`ctx.delete(...)` to preserve metadata from other libraries.

### 4.3. Which Overload Should You Choose?

| Case | Recommended |
| --- | --- |
| Attach a few known values to the subscription | `contextWrite(Context.of("key", value))` |
| Write a key based on existing downstream data | `contextWrite(ctx -> ctx.put("key", ...))` |
| Conditionally delete or modify | `contextWrite(ctx -> ctx.delete("key"))` / lambda |
| Merge multiple keys already in a `ContextView` | `contextWrite(contextView)` or `ctx.putAll(contextView)` |
| Read data from Context to produce `onNext` | `Mono.deferContextual(...)`; **not** `contextWrite` |
| Transform payload `T` into `R` | `map`/`flatMap`; **not** `contextWrite` |

A `contextWrite` does not turn `Mono<T>` into `Mono<Context>`: the Publisher's element type `T` stays unchanged. Only the metadata available to upstream changes.

## 5. Context Propagation Direction: Downstream → Upstream

### 5.1. Two Opposite Directions in One Pipeline

~~~text
             Data direction (onNext): top → bottom

     Mono.deferContextual(ctx -> ...)   [READ]
                    |
                  map(...)
                    |
      contextWrite(ctx -> ctx.put(...)) [WRITE]
                    |
              subscribe()

             Context direction: bottom → top
                 at subscription time
~~~

`subscribe()` at the bottom establishes the `Subscriber` chain. As the subscription is built from downstream up to upstream, each `contextWrite` **contributes a new Context** to the Subscriber above it. When data flows downward (`onNext`), Context is **not** an object carried alongside each item; operators query their downstream subscriber's Context according to their position/relationship.

Therefore, when reading code top-to-bottom, you may see `contextWrite` at the bottom while the metadata is already available to `deferContextual` above it.

### 5.2. Write Below, Read Above: Correct

~~~java
Mono<String> correct = Mono.deferContextual(ctx ->
        Mono.just("trace=" + ctx.getOrDefault("traceId", "missing")))
    .contextWrite(ctx -> ctx.put("traceId", "T-1"));

// Upon subscribe: trace=T-1
~~~

### 5.3. Write Above, Read Below: Not Visible

~~~java
Mono<String> notVisible = Mono.just("payload")
    .contextWrite(ctx -> ctx.put("traceId", "T-1"))
    .flatMap(ignored ->
        Mono.deferContextual(ctx ->
            Mono.just("trace=" + ctx.getOrDefault("traceId", "missing"))));

// Upon subscribe: trace=missing
~~~

Here `contextWrite` sits **upstream** of `flatMap`, so it only changes Context for its own upstream; the `deferContextual` created inside `flatMap` **downstream** does not receive this key.

This is the most common placement mistake: learners assume Context is "attached to the payload data" and automatically rides along with `onNext`. In reality, **where the operator is placed** determines the effective scope.

### 5.4. Quick Placement Rule

If you want **the source and most of the pipeline** to read the request ID, place `contextWrite` near the end of the chain, right before the subscription point managed by the application or framework:

~~~java
Mono<Response> response = service.process(command)
    .contextWrite(ctx -> ctx.put("requestId", requestId));
~~~

`Response`, `command`, `service`, and `requestId` in this snippet are illustrative domain names, not a standalone program. `contextWrite` does not need to be placed at every operator; one well-placed call is enough to supply the key to everything upstream within that scope.

## 6. Duplicate Keys and Ordering of Multiple `contextWrite` Calls

### 6.1. "Closer to the Read" Can Override "Farther Away"

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just(ctx.<String>get("color")))
    .contextWrite(ctx -> ctx.put("color", "blue"))
    .contextWrite(ctx -> ctx.put("color", "red"));

// Result: blue
~~~

Progression at subscription time (reading **bottom-to-top**):

1. `contextWrite(color=red)` at the bottom creates a Context with `red`.
2. `contextWrite(color=blue)` above it receives the `red` Context and creates a **new** Context with `blue`.
3. `deferContextual` further above reads `blue`.

Thus, the same key can have different values across **sections of a pipeline**, without all operators sharing a single global mutable map.

### 6.2. Two Readers on Opposite Sides See Two Values

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just("upper=" + ctx.<String>get("key")))
    .contextWrite(ctx -> ctx.put("key", "NEAR_SOURCE"))
    .flatMap(upper ->
        Mono.deferContextual(ctx ->
            Mono.just(upper + ", lower=" + ctx.<String>get("key"))))
    .contextWrite(ctx -> ctx.put("key", "NEAR_SUBSCRIBER"));

// upper=NEAR_SOURCE, lower=NEAR_SUBSCRIBER
~~~

Explanation: the reader at the top of the chain sees the Context overridden **near the source**; the reader inside the downstream `flatMap` sees the key from the Context **near the final subscriber**. There is no race condition here: each position has the Context view matching its subscriber relationship.

### 6.3. Watch Out for Key Collisions Between Libraries

`Context` allows `Object` keys. Using common strings like `"user"`, `"id"`, or `"token"` can collide with keys used by other libraries.

~~~java
final class TraceKeys {
    private TraceKeys() {}
    static final Object CORRELATION_ID = new Object();
}
~~~

Using the same **constant key object** for both writing and reading within the same subsystem reduces collisions with other libraries:

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just(ctx.<String>get(TraceKeys.CORRELATION_ID)))
    .contextWrite(ctx -> ctx.put(TraceKeys.CORRELATION_ID, "R-1"));
~~~

Note that `TraceKeys` here is an illustrative class that must be defined alongside application code; an `Object` key uses Java `Object` **identity** for `equals`/`hashCode`, so you must not create a fresh `new Object()` on each read.

## 7. Write Per Subscription, Not Once for the Whole Publisher

### 7.1. One Source, Two Subscribers, Two Contexts

~~~java
Mono<String> shared = Mono.deferContextual(ctx ->
    Mono.just("rid=" + ctx.<String>get("rid")));

Mono<String> first = shared.contextWrite(Context.of("rid", "REQ-A"));
Mono<String> second = shared.contextWrite(Context.of("rid", "REQ-B"));

// first emits rid=REQ-A
// second emits rid=REQ-B
~~~

`shared` is the same Publisher source, while `first` and `second` are two pipelines with Context attached **per subscription**. Do not use a global mutable variable to hold `rid` per request: user A could end up reading B's `rid`.

### 7.2. The Function Runs According to the Subscription Lifecycle

~~~java
Mono<String> source = Mono.deferContextual(ctx ->
    Mono.just(ctx.<String>get("rid")));

Mono<String> prepared = source.contextWrite(ctx ->
    ctx.put("rid", java.util.UUID.randomUUID().toString())
);
~~~

The UUID computation lives **inside** the `contextWrite` function, so it runs when creating the subscription's context rather than when constructing the `prepared` variable. When the application subscribes again with an independent subscription, the function can generate a new UUID.

However, do not infer that "each `onNext` gets its own UUID": Context is not a per-item value generator. If you need a per-element ID, generate it inside `map`/`flatMap` or the appropriate data operator.

### 7.3. Writing Inside a `flatMap` Branch: Local Scope

~~~java
Mono<String> nested = Mono.just("start")
    .flatMap(value ->
        Mono.deferContextual(ctx ->
            Mono.just("inner=" + ctx.<String>get("scope")))
        .contextWrite(ctx -> ctx.put("scope", "INNER")))
    .flatMap(value ->
        Mono.deferContextual(ctx ->
            Mono.just(value + ", outer=" + ctx.<String>get("scope"))))
    .contextWrite(ctx -> ctx.put("scope", "OUTER"));

// Result: inner=INNER, outer=OUTER
~~~

`contextWrite(scope=INNER)` applies to the inner Publisher of the first `flatMap`; it does not "globally change the Context" of downstream or sibling branches. The outer `contextWrite(scope=OUTER)` affects the main subscription and is inherited by child branches until a child branch overrides it.

Understanding this scope prevents one library component from accidentally altering another component's metadata.

## 8. Reading Back to Verify: `deferContextual` and `transformDeferredContextual`

### 8.1. Reading at the Source with `Mono.deferContextual`

~~~java
Mono<String> publisher = Mono.deferContextual(ctx ->
        Mono.just("tenant=" + ctx.getOrDefault("tenantId", "public")))
    .contextWrite(Context.of("tenantId", "tenant-42"));
~~~

All access must happen inside the lambda at **subscription time**, because Context is not a variable you fetch upfront and store into an arbitrary field at assembly time.

If you need to read inside a `flatMap`, also use `Mono.deferContextual` inside the branch:

~~~java
Mono<String> decorated = Mono.just("payload")
    .flatMap(payload ->
        Mono.deferContextual(ctx ->
            Mono.just(payload + "@" + ctx.<String>get("requestId"))))
    .contextWrite(Context.of("requestId", "REQ-1"));
~~~

### 8.2. Reading on a Flux with `Flux.deferContextual`

~~~java
Flux<String> rows = Flux.deferContextual(ctx -> {
    String prefix = ctx.getOrDefault("prefix", "row");
    return Flux.range(1, 3)
        .map(i -> prefix + "-" + i);
}).contextWrite(Context.of("prefix", "record"));
~~~

This source emits `record-1`, `record-2`, `record-3`. `ContextView` can be captured in the lambda and used inside operations created for that branch; avoid storing a global context variable and reusing it across multiple subscriptions.

### 8.3. Reading Mid-Chain with `transformDeferredContextual`

~~~java
Flux<String> output = Flux.range(1, 3)
    .transformDeferredContextual((flux, ctx) ->
        flux.map(i -> ctx.getOrDefault("prefix", "item") + "-" + i))
    .contextWrite(Context.of("prefix", "P"));
~~~

Upon subscription, downstream receives `P-1`, `P-2`, `P-3`. This operator is useful when a mid-chain transformation needs subscription-scoped `ContextView` access without wrapping every item in a `Mono.deferContextual`.

**Distinction:** `transformDeferredContextual` is a tool for **reading Context and building a data transformation**; it is not a metadata-writing operator. `contextWrite` keeps the writing role.

## 9. Complete Java 17+ Program with Deterministic Output

This example uses **Project Reactor Core 3.8.8**, JDK 17+, and Maven. We use finite, synchronous sources without changing schedulers so stdout is deterministic.

Project layout:

~~~text
reactor-context-write-demo/
├── pom.xml
└── src/main/java/example/ContextWriteDemo.java
~~~

### 9.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-context-write-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.ContextWriteDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 9.2. `src/main/java/example/ContextWriteDemo.java`

~~~java
package example;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

public final class ContextWriteDemo {

    public static void main(String[] args) {
        // A. Write via function, read upstream.
        Mono<String> greeting = Mono.deferContextual(ctx ->
                Mono.just("Hello " + ctx.<String>get("name")))
            .contextWrite(ctx -> ctx.put("name", "Linh"));
        System.out.println("A: " + greeting.block());

        // B. Written too high: downstream flatMap cannot see it.
        Mono<String> wrong = Mono.just("ready")
            .contextWrite(ctx -> ctx.put("trace", "T-1"))
            .flatMap(value ->
                Mono.deferContextual(ctx ->
                    Mono.just("trace=" + ctx.getOrDefault("trace", "missing"))));
        System.out.println("B: " + wrong.block());

        // C. Place write below flatMap: read succeeds.
        Mono<String> right = Mono.just("ready")
            .flatMap(value ->
                Mono.deferContextual(ctx ->
                    Mono.just("trace=" + ctx.getOrDefault("trace", "missing"))))
            .contextWrite(Context.of("trace", "T-1"));
        System.out.println("C: " + right.block());

        // D. Two writes with the same key: closer to source overrides.
        Mono<String> precedence = Mono.deferContextual(ctx ->
                Mono.just("region=" + ctx.<String>get("region")))
            .contextWrite(ctx -> ctx.put("region", "near"))
            .contextWrite(ctx -> ctx.put("region", "far"));
        System.out.println("D: " + precedence.block());

        // E. Two subscriptions on the same source have separate contexts.
        Mono<String> shared = Mono.deferContextual(ctx ->
            Mono.just("rid=" + ctx.<String>get("rid")));
        System.out.println("E1: " +
            shared.contextWrite(Context.of("rid", "A")).block());
        System.out.println("E2: " +
            shared.contextWrite(Context.of("rid", "B")).block());

        // F. Write for Flux, read mid-chain.
        Flux<String> transformed = Flux.range(1, 3)
            .transformDeferredContextual((flux, ctx) ->
                flux.map(i ->
                    ctx.getOrDefault("prefix", "item") + "-" + i))
            .contextWrite(Context.of("prefix", "row"));
        System.out.println("F: " + transformed.collectList().block());

        // G. Delete key at a boundary for upstream.
        Mono<String> removed = Mono.deferContextual(ctx ->
                Mono.just("has secret=" + ctx.hasKey("secret")))
            .contextWrite(ctx -> ctx.delete("secret"))
            .contextWrite(Context.of("secret", "old"));
        System.out.println("G: " + removed.block());

        // H. Write inside inner publisher affects only inner.
        Mono<String> nested = Mono.just("start")
            .flatMap(value -> Mono.deferContextual(ctx ->
                    Mono.just("inner=" + ctx.<String>get("scope")))
                .contextWrite(ctx -> ctx.put("scope", "INNER")))
            .flatMap(value -> Mono.deferContextual(ctx ->
                Mono.just(value + ", outer=" + ctx.<String>get("scope"))))
            .contextWrite(Context.of("scope", "OUTER"));
        System.out.println("H: " + nested.block());
    }
}
~~~

Run from the `reactor-context-write-demo` directory:

~~~bash
mvn -q compile exec:java
~~~

**Expected stdout:**

~~~text
A: Hello Linh
B: trace=missing
C: trace=T-1
D: region=near
E1: rid=A
E2: rid=B
F: [row-1, row-2, row-3]
G: has secret=false
H: inner=INNER, outer=OUTER
~~~

Interpretation of results:

- **A:** `contextWrite` sits below `deferContextual`, so the `name` key reaches the read site.
- **B:** the write sits above `flatMap`, so the downstream inner read does not see `trace`.
- **C:** swapping the positions allows `flatMap` to see `trace`.
- **D:** the Context closer to the reader overrides the value from the section farther from the reader.
- **E:** each independent subscription has its own metadata even though the `shared` source is the same.
- **F:** `transformDeferredContextual` reads Context mid-chain on a `Flux`.
- **G:** `delete` creates a new Context without `secret` for upstream.
- **H:** a child branch's context does not change the context of another downstream branch.

`block()` in the example is solely so `main` can observe the final results. **Do not** call `block()` on non-blocking Spring WebFlux handler threads; on a server, return or compose the Publisher so the framework manages the subscription.

## 10. Spring WebFlux: Attaching Request ID with `contextWrite`

A classic use case is a correlation ID for logging or tracing across multiple layers of the same HTTP request. Using a `WebFilter`, you can add the ID to the Context of the pipeline subscribed to by the framework.

### 10.1. Attaching at the Request Boundary with `WebFilter`

This is **illustrative code** belonging to an application that already has the `spring-boot-starter-webflux` dependency, corresponding Spring imports, and bean configuration; **it is not part of the standalone Reactor Core program in section 9**:

~~~java
@Configuration
public class RequestContextConfig {

    @Bean
    public WebFilter requestIdFilter() {
        return (exchange, chain) -> {
            String requestId = java.util.UUID.randomUUID().toString();

            return chain.filter(exchange)
                .contextWrite(ctx ->
                    ctx.put("requestId", requestId));
        };
    }
}
~~~

`chain.filter(exchange)` returns a Publisher representing request handling. `contextWrite` downstream of this chain supplies `requestId` to Context-reading operators inside the upstream request processing.

In a reactive service, you can read it with:

~~~java
public Mono<String> identifyRequest() {
    return Mono.deferContextual(ctx ->
        Mono.just("requestId=" +
            ctx.getOrDefault("requestId", "not-provided")));
}
~~~

A controller can return `identifyRequest()` as part of the response, or use the request ID for logging/tracing. **Do not call `subscribe()` separately in a handler** to read Context, because that creates another subscription and may not inherit the HTTP request's Context.

### 10.2. Avoid Putting Sensitive Metadata Arbitrarily

Context can travel through many operators and libraries on the same subscription. Do not treat Context as a secret store that is automatically encrypted or access-controlled. For tokens or identities:

- Only put metadata that has been verified and is genuinely needed; avoid logging raw tokens/passwords.
- Use official security mechanisms such as **Reactive Spring Security Context** when the application uses Spring Security, instead of arbitrarily creating keys like `"user"` or `"role"` and treating them as proof of authentication.
- Keep key ownership clear to prevent other libraries from overwriting them unintentionally.
- If you must carry data with complex lifecycles or resources, use appropriate data structures and cleanup mechanisms; do not treat Context as a full transaction or resource scope.

### 10.3. Why Is `contextWrite` Better Than `ThreadLocal` in a Reactive Pipeline?

In WebFlux, a workflow can run across `publishOn`, `subscribeOn`, I/O callbacks, and different threads. `ThreadLocal` is bound to a **thread**, so if set on the initial HTTP thread, an operator on another thread will not automatically see the value. Reactor Context is bound to a **subscription**, allowing Reactor operators to read metadata in the right scope via `ContextView`.

~~~java
Mono<String> acrossThreads = Mono.deferContextual(ctx ->
        Mono.just(ctx.<String>get("requestId")))
    .publishOn(reactor.core.scheduler.Schedulers.parallel())
    .contextWrite(ctx -> ctx.put("requestId", "R-42"));
~~~

Here the example reads Context via the subscriber, so switching threads does not lose Context metadata within the proper scope. **Do not infer that `ThreadLocal` is also propagated automatically.** Reactor/Micrometer provides a separate context propagation mechanism and configurable automatic mode, which is a different integration—not the default effect of a single `contextWrite` call.

## 11. Limitations and Behaviors to Understand Clearly

### 11.1. `contextWrite` Does Not Change Emitted Values

~~~java
Flux<Integer> numbers = Flux.range(1, 3)
    .contextWrite(Context.of("traceId", "T-1"));
~~~

`numbers` still emits `1, 2, 3`. Context data does not turn into new `onNext` elements and does not make the `Flux` emit an extra `traceId` value. If you want the payload to contain `traceId`, you must build a new payload using `map`/`flatMap` combined with reading Context.

### 11.2. Metadata Flows Upstream, Not Magically Down Every Branch

`contextWrite` only affects **the upstream connected to that subscription**. It does not automatically affect a `repository.save(...).subscribe()` statement that you invoke separately inside a callback without composing it as a child source of the Publisher.

For `flatMap`, the context of the upstream/child branch is determined by that child branch's subscriber; a `contextWrite` inside that branch does not automatically alter the Context of the outer main pipeline.

### 11.3. Context Does Not Replace Concurrency Management

A Context containing `userId` does not serialize two tasks for the same user, does not grant locks, does not provide transactions, does not provide backpressure, and does not decide the Scheduler. It simply provides key–value entries at the appropriate points in the pipeline.

### 11.4. `subscribeOn`/`publishOn` Are Not Ways to Write Context

- `publishOn` switches the thread for processing downstream signals.
- `subscribeOn` changes where subscription and corresponding upstream execution take place.
- `contextWrite` supplies Context to upstream.
- `deferContextual` reads Context at subscription time.

You can combine them in the same pipeline, but each operator serves a distinct purpose. Changing Schedulers does not mutate or erase Context by definition, although ThreadLocal-based integrations require an appropriate bridge.

### 11.5. Writing Context Cannot Retroactively Attach Info to Already-Completed Upstream Work

If a library has **detached the subscription** via a separate `subscribe()`, or you performed side effects **before assembly**, adding `contextWrite` later cannot "re-attach" metadata to events that already ran. Similarly, writing `Mono.just(blockingCall())` and then adding `contextWrite` does not delay `blockingCall`: Java evaluates the argument to `just` eagerly.

### 11.6. Errors, Cancellation, and Request Demand Are Not Changed by `contextWrite`

`contextWrite` does not swallow `onError`, does not turn an infinite source into a finite one, does not increase demand, and does not create an independent subscriber. It supplies metadata along the subscription relationship; lifecycle and backpressure remain governed by the Publisher/Subscriber and other operators. If upstream errors, the error still propagates normally unless a dedicated error-handling operator handles it.

### 11.7. Context Is Not Automatically Propagated Across Arbitrary APIs

For libraries not integrated with Reactor, callbacks from `CompletableFuture`, `Executor`, or other frameworks do not automatically understand Reactor's `ContextView`. You may need to pass data explicitly or use an appropriate context-propagation bridge. Do not expect `contextWrite` to automatically make the entire Java application context-aware.

## 12. Common Mistakes and Fixes

**Mistake 1 — Placing `contextWrite` above the read site.** Reactor Context propagates from the final subscriber to upstream; place the write below the reader or inside the properly scoped branch.

**Mistake 2 — Thinking `contextWrite` "adds a field to each item."** No. It changes Context, not the element `T`. To transform the payload, use `map`/`flatMap`.

**Mistake 3 — Ignoring the return value of `Context.put`.** Context is immutable: `ctx.put(...)` creates a new Context. Inside `contextWrite(Function)`, you must `return ctx.put(...)`.

**Mistake 4 — Returning a brand-new Context and losing downstream metadata.** `contextWrite(ctx -> Context.of("id", "X"))` can drop keys already attached by other libraries. Use `ctx.put(...)` to preserve unchanged entries.

**Mistake 5 — Calling `ctx.get("key")` when the key may be absent.** This can fail while reading Context. Use `getOrDefault`/`getOrEmpty` or check `hasKey` if the key is optional.

**Mistake 6 — Confusing "closer to source" and "closer to subscriber."** With two `contextWrite` calls for the same key, the write closer to the reader—executed after receiving the downstream Context—overrides the earlier one.

**Mistake 7 — Storing the request ID in a field of a singleton Spring service.** Concurrent requests can interleave and leak or overwrite IDs. Use subscription-bound Context.

**Mistake 8 — Treating Context as `ThreadLocal`.** `ThreadLocal` changes per thread, whereas Context is bound to the subscriber. Switching threads does not automatically carry every `ThreadLocal`; use a bridge if needed.

**Mistake 9 — Putting `contextWrite` inside an inner `flatMap` and expecting every other branch to change.** Context in a child branch is locally scoped; it is not a shared mutable map for the whole stream.

**Mistake 10 — Using generic string keys like `"id"` or `"token"` in a library.** Easy to collide with other subsystems. Use dedicated key constants/objects and namespacing conventions.

**Mistake 11 — Putting a mutable object into Context and assuming it is concurrency-safe.** Context is immutable at the key–value map level, not a deep copy of values; keep values immutable or manage synchronization separately.

**Mistake 12 — Logging the entire Context.** This can expose sensitive data. Log only permitted keys with proper masking.

**Mistake 13 — Calling `subscribe()` manually in a controller to read metadata.** The new subscription has its own Context and easily loses the link to the request. Return the Publisher for WebFlux to handle.

**Mistake 14 — Thinking `contextWrite` grants access permissions.** Self-written metadata is not authentication proof. Authentication and authorization must come from a trusted mechanism.

**Mistake 15 — Using a context with a mutable key/value to pass data between two subscribers.** Each subscriber has its own Context; if you need true shared data, design a controlled shared source/object with an explicit contract.

**Mistake 16 — Checking thread names instead of Context.** Threads can be reused; request IDs should come from `ContextView` or context-propagation tools, not be inferred from thread names.

## 13. Self-Check Exercises

1. What does `Mono.deferContextual(ctx -> Mono.just(ctx.getOrDefault("k","?"))).contextWrite(ctx -> ctx.put("k","X"))` emit? **`X`.**
2. If you reorder it to `Mono.just("a").contextWrite(ctx -> ctx.put("k","X")).flatMap(v -> Mono.deferContextual(ctx -> Mono.just(ctx.getOrDefault("k","?"))))`, what does it emit? **`?`**, because the write is upstream of the reader's position.
3. Given `Context c = Context.of("k","a"); c.put("k","b");`, what does `c.get("k")` return afterward? **`a`**; `c` was not reassigned.
4. Two `contextWrite` calls write the same key: the lower one writes `A`, and the upper one writes `B`. What does a reader above both see? **`B`**, because the write closer to the reader overrides.
5. Can `Mono.deferContextual` be used to extract the value immediately at assembly time, before subscribe? **No**. It provides data when subscription occurs.
6. A shared `Mono` is used by two subscribers with `Context.of("rid","A")` and `Context.of("rid","B")`. Must they see the same `rid`? **No**; per subscription, they see `A` and `B` respectively.
7. Does `contextWrite(Context.of("trace","T-1"))` cause `Flux.range(1,3)` to emit a fourth element carrying `trace`? **No**.
8. In WebFlux, should you call `subscribe()` in a controller to pass Context to a background service? **No**. Compose the Publisher and use `contextWrite` at the appropriate boundary so the framework maintains the lifecycle.
9. Does switching threads with `publishOn` cause Reactor Context to be lost by contract? **No**; Context is subscriber-bound. However, `ThreadLocal` is not automatically carried with it.
10. What problem can `ctx -> Context.of("newKey","V")` cause? **It drops keys already present from downstream**. Prefer `ctx.put("newKey","V")`.
11. What happens with `ctx.get("missing")`? **It may throw `NoSuchElementException`**, so handle missing keys when allowed.
12. Does putting a mutable `HashMap` as a Context value make the map itself immutable? **No**.
13. Why use a static key object instead of an overly common string? **Reduces the risk of key collisions across libraries/subsystems**; the same constant must be used for both reading and writing.
14. Can `contextWrite` be used to automatically authenticate a request by writing `role=ADMIN`? **No**. Self-written context data is not proof of authentication; use reactive Spring Security and trusted contracts.

## 14. Summary and References

- **Write:** `contextWrite(Context.of("key", value))` or `contextWrite(ctx -> ctx.put("key", value))`.
- **Read:** `Mono.deferContextual`, `Flux.deferContextual`, or `transformDeferredContextual`.
- **Timing:** Context is established at subscription time via the Subscriber/Subscription path.
- **Propagation direction:** from **downstream to upstream**; the write must sit below the section that needs to read it.
- **Immutability:** `put` and `delete` return a new Context; never discard the return value.
- **Isolation:** Context is bound to the subscription, not to a thread or shared application-wide.
- **Scope:** a key written in an inner branch does not automatically change all other branches.
- **Limits:** `contextWrite` does not transform payloads, make I/O non-blocking, guarantee `ThreadLocal` propagation, or authenticate users.

Official references:

1. [Project Reactor Reference — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): `Context`, `ContextView`, the two overloads of `contextWrite`, subscription direction, operator placement examples.
2. [Project Reactor API — Mono.contextWrite and deferContextual](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): signatures, writing context for upstream, creating a Mono from Context.
3. [Project Reactor API — Flux.contextWrite and transformDeferredContextual](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): how to write and read in Flux.
4. [Project Reactor API — Context](https://projectreactor.io/docs/core/release/api/reactor/util/context/Context.html) and [ContextView](https://projectreactor.io/docs/core/release/api/reactor/util/context/ContextView.html): immutability, `put`/`delete`/`getOrDefault`/`getOrEmpty`, key reading rules.
5. [Project Reactor Reference — Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html): optional bridge between Context and `ThreadLocal` (depending on dependency/mode).
6. [Spring Framework — WebFlux Web Filters](https://docs.spring.io/spring-framework/reference/web/webflux/filters.html): `WebFilter` position in the request lifecycle.
