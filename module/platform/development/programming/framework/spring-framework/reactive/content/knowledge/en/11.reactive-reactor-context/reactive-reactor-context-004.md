# Reading Context with `deferContextual` in Project Reactor

## 1. What Is Reactor Context Used For?

In a Spring WebFlux application, a request often passes through multiple layers: controller, service, repository, and outbound HTTP calls. Those layers may run on different threads, yet still need access to certain **metadata bound to the current subscription/request**, such as:

- `traceId` or `correlationId` to correlate logs and distributed traces.
- `tenantId` to identify the tenant in a multi-tenant system.
- Authentication/authorization information supported by the framework.
- Reactive transaction metadata or observability information.

Project Reactor provides **Reactor Context** to propagate metadata per **subscription** throughout a reactive pipeline. To read data from Context when a Publisher is subscribed to, use `deferContextual`.

Short example:

```java
Mono<String> tenant = Mono.deferContextual(context ->
        Mono.just(context.get("tenantId"))
).contextWrite(context -> context.put("tenantId", "tenant-a"));
```

When a subscriber subscribes, `deferContextual` reads `tenantId` from the subscription's Context and emits `"tenant-a"`.

Key distinctions:

- **Reactor Context** is a subscription-bound metadata structure propagated through Reactor operators.
- **Java `ThreadLocal`** binds a value to a thread. Threads can change in a reactive pipeline, so you cannot assume `ThreadLocal` metadata will follow the request.
- **Method parameters** are the explicit way to pass data between functions. For primary business data, passing via parameters is usually clearer and easier to test than using Context.
- **`deferContextual`** is a way to create a Publisher based on Context at subscription time; it does not add data to Context itself and does not create threads.

Context fits **cross-cutting metadata spanning layers**; it should not be turned into a storage bucket for all of a request's business data.

## 2. `ContextView` and How to Read Values

`deferContextual` receives a `ContextView`, which is the read-only interface of Reactor Context. Common operations:

| API | Meaning | When to use |
|---|---|---|
| `context.get(key)` | Retrieves the value by key; throws if the key does not exist | Required key, where a missing key is a configuration/contract error |
| `context.getOrDefault(key, defaultValue)` | Retrieves the value or uses a default | Optional metadata |
| `context.hasKey(key)` | Checks whether the key exists | Conditional branching |
| `context.isEmpty()` | Checks whether the Context is empty | Diagnostics or default logic |
| `context.stream()` | Iterates over Context entries | Controlled debugging; avoid logging sensitive data |

`ContextView` is **read-only**. Do not call `put` on `ContextView`; to add or replace values, use `contextWrite` with `Context`.

Example reading a required key:

```java
Mono<String> traceId = Mono.deferContextual(context ->
        Mono.just(context.get("traceId"))
);
```

If the subscriber does not supply `"traceId"`, `get` throws `NoSuchElementException` while constructing the Publisher inside `deferContextual`; Reactor translates that exception into an `onError` signal.

For an optional key:

```java
Mono<String> traceId = Mono.deferContextual(context ->
        Mono.just(context.getOrDefault("traceId", "trace-unknown"))
);
```

Or explicit checking:

```java
Mono<String> traceId = Mono.deferContextual(context -> {
    if (context.hasKey("traceId")) {
        return Mono.just(context.get("traceId"));
    }
    return Mono.just("trace-unknown");
});
```

Choose a consistent policy. If a missing `tenantId` could cause accessing the wrong tenant, do not silently fall back to a default tenant; treat it as a required failure and return an appropriate error.

## 3. How Does `Mono.deferContextual` Work?

Usage signature:

```java
static <T> Mono<T> Mono.deferContextual(
        Function<ContextView, ? extends Mono<? extends T>> factory);
```

This is a **shortened signature to explain generics**, not a method declaration to copy into a class. The factory receives a `ContextView` and returns another `Mono`. The factory is invoked **at subscription time** with that subscriber's Context.

Processing flow:

```text
Subscriber
    |
    | subscribes with its own Context
    v
deferContextual(contextView -> ...)
    |
    | reads key from ContextView
    | creates the appropriate Mono
    v
Publisher returned by factory
    |
    | onNext / onComplete or onError
    v
Downstream Subscriber
```

Example:

```java
Mono<String> greeting = Mono.deferContextual(context -> {
    String name = context.getOrDefault("userName", "guest");
    return Mono.just("Hello, " + name);
});
```

When `greeting` is declared, the factory has not run yet. When a subscriber subscribes, Reactor supplies the `ContextView` belonging to that subscription, and the factory creates the corresponding Publisher.

**Each subscription can see a different Context** even when sharing the same Publisher variable:

```java
Mono<String> greeting = Mono.deferContextual(context ->
        Mono.just("Hello, " + context.getOrDefault("userName", "guest"))
);

String first = greeting
        .contextWrite(context -> context.put("userName", "An"))
        .block();

String second = greeting
        .contextWrite(context -> context.put("userName", "Binh"))
        .block();
```

The results are `"Hello, An"` and `"Hello, Binh"`, respectively. These are two independent subscriptions; `contextWrite` does not mutate a shared Context variable across all subscribers.

`block()` in the example is only for illustrating how to obtain results in a console/test program. Do not call `block()` in a WebFlux controller or service to wait for reactive results.

## 4. `Flux.deferContextual` for Reading Context in Multi-Element Streams

With `Flux`, the factory can return a `Publisher<T>` and read metadata once to build the entire sequence:

```java
Flux<String> events = Flux.deferContextual(context -> {
    String requestId = context.getOrDefault("requestId", "anonymous");

    return Flux.just("accepted", "processing", "completed")
            .map(event -> requestId + ":" + event);
});
```

When the subscriber sets `requestId = "req-42"` in Context, the emitted values are:

```text
req-42:accepted
req-42:processing
req-42:completed
```

Context is read when creating the inner Publisher for the subscription. If multiple items in the same stream need the same metadata, you can read Context once in the factory and capture the value in the `map` lambda. If you need to read Context inside individual child Publishers or child subscriptions, place `deferContextual` at those exact boundaries.

Do not confuse `Flux.deferContextual` with automatically attaching Context to each object. The emitted values remain `T`; Context is accessed separately via the subscription.

## 5. How Do `defer` and `deferContextual` Differ?

Both APIs defer Publisher creation, but they serve different purposes:

| API | What does the factory receive? | When appropriate |
|---|---|---|
| `Mono.defer(() -> publisher)` | Receives no arguments | Need to create a fresh Publisher per subscription, without reading Context |
| `Mono.deferContextual(ctx -> publisher)` | Receives the subscription's `ContextView` | Need to create a Publisher based on subscriber metadata |
| `Flux.defer(() -> publisher)` | Receives no arguments | Create a Flux per subscription |
| `Flux.deferContextual(ctx -> publisher)` | Receives `ContextView` | Create a Flux based on Context |

`defer` example:

```java
Mono<String> value = Mono.defer(() -> {
    String generated = createValue();
    return Mono.just(generated);
});
```

`createValue()` is invoked upon subscription, but there is no way to read Context via this factory's parameter.

`deferContextual` example:

```java
Mono<String> value = Mono.deferContextual(context -> {
    String tenant = context.get("tenantId");
    return Mono.just(createValueForTenant(tenant));
});
```

Here the factory is both deferred and able to read the subscriber's `tenantId`.

If you only need to read Context in one operator, you can use other Context-aware operators or place `deferContextual` at that exact spot. There is no need to wrap the entire pipeline in `deferContextual` without reason.

## 6. `contextWrite`: Putting Data into Context

`deferContextual` only reads; to add metadata, use `contextWrite`.

### 6.1. Adding a Single Key

```java
Mono<String> result = Mono.deferContextual(context ->
        Mono.just(context.get("traceId"))
).contextWrite(context ->
        context.put("traceId", "trace-001")
);
```

`Context` is **immutable**: `put` returns a new Context. Return the new Context from the `contextWrite` lambda; do not treat this operation like mutating a mutable map.

### 6.2. Adding Multiple Keys with `Context.of`

```java
import reactor.util.context.Context;

Mono<String> result = Mono.deferContextual(context ->
        Mono.just(context.get("tenantId") + "/" + context.get("traceId"))
).contextWrite(Context.of(
        "tenantId", "tenant-a",
        "traceId", "trace-001"
));
```

`Context.of` has overloads for creating a Context from key/value pairs. For many keys or merge logic, use the `contextWrite` lambda.

### 6.3. Conditionally Adding a Key

```java
Mono<String> result = Mono.deferContextual(context ->
        Mono.just(context.getOrDefault("locale", "vi"))
).contextWrite(context -> {
    if (context.hasKey("locale")) {
        return context;
    }
    return context.put("locale", "vi");
});
```

The snippet above preserves an existing `locale` value and only adds a default if absent. Because Context is immutable, both branches return a valid Context.

### 6.4. Overwriting Duplicate Keys

```java
Mono<String> result = Mono.deferContextual(context ->
        Mono.just(context.get("tenantId"))
).contextWrite(context -> context.put("tenantId", "tenant-local"));
```

Calling `put` with the same key replaces that key's value in the returned new Context. Be careful with framework-managed keys: accidentally overwriting a security or transaction key can alter application behavior.

## 7. Context Propagation Direction: Downstream Back Up to Upstream

This is the single most important rule when reading code: **Context propagates from the subscriber back upstream**, opposite to the flow of `onNext` data.

```text
Data flow:
source ── onNext ──> map ── onNext ──> subscriber

Context flow:
source <── Context ── map <── Context ── subscriber
```

Therefore:

```java
Mono<String> source = Mono.deferContextual(context ->
        Mono.just(context.get("traceId"))
);

Mono<String> result = source
        .contextWrite(context -> context.put("traceId", "req-100"));
```

`contextWrite` sits **downstream** of `deferContextual` in the chain declaration order. When subscription enters, `contextWrite` adds the key before Context reaches the source, so `deferContextual` reads `"req-100"`.

Do not assume Context flows in the same direction as `onNext`. The following example is a common source of confusion:

```java
Mono<String> source = Mono.deferContextual(context ->
        Mono.just(context.getOrDefault("traceId", "missing"))
);

Mono<String> result = source
        .contextWrite(context -> context.put("traceId", "req-100"))
        .map(value -> value);
```

Here `map` sits after `contextWrite` in data-flow order. The Context set by `contextWrite` is used by operators upstream of it; `map` downstream is not where keys from that write are read. If you want to read Context, place `deferContextual` appropriately upstream and `contextWrite` downstream of it.

When there are multiple `contextWrite` calls, declaration order and duplicate keys affect what the source sees. Avoid multiple layers writing the same key without a clear convention. Write tests for the final value instead of relying on intuition about ordering.

## 8. Context Is Not ThreadLocal

Reactor Context propagates with the subscription, not bound to a thread. Therefore, inside a Reactor pipeline, Context data can be read across operators even when execution switches threads via schedulers.

Example:

```java
Mono<String> result = Mono.deferContextual(context ->
        Mono.just("trace=" + context.get("traceId"))
).publishOn(reactor.core.scheduler.Schedulers.parallel())
 .map(value -> value + " processed")
 .contextWrite(context -> context.put("traceId", "trace-77"));
```

The Context set by `contextWrite` can be read by `deferContextual`; `publishOn` moves downstream signal processing to another scheduler. You do not need to copy `traceId` into a `ThreadLocal` to keep Context alive inside the Reactor pipeline.

However:

- Do not assume Context automatically becomes a `ThreadLocal` for libraries outside Reactor.
- If invoking callbacks on a custom executor or an API not integrated with Reactor, check that integration's context propagation mechanism.
- MDC logging's `ThreadLocal` is not automatically synonymous with Reactor Context. To include trace metadata in logs, use a logging/observability integration or context-propagation setup compatible with your application version and configuration.
- Do not use thread names to identify tenants or users. Threads can be reused across many subscriptions.

Context and `ThreadLocal` solve two different problems; do not blindly substitute one for the other.

## 9. Runnable Java 17+ Example with Project Reactor

This example uses a `Mono` Publisher reused across multiple subscribers, each supplying its own `traceId` and `tenantId`. The second example uses `Flux.deferContextual` to attach a request ID to events.

Directory layout:

```text
reactor-context-demo/
├── pom.xml
└── src/main/java/demo/Main.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactor-context-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/Main.java`:

```java
package demo;

import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

public final class Main {
    public static void main(String[] args) {
        // One shared pipeline, different Context per subscription.
        Mono<String> description = Mono.deferContextual(context -> {
            String traceId = context.getOrDefault("traceId", "no-trace");
            String tenantId = context.getOrDefault("tenantId", "public");
            return Mono.just("trace=" + traceId + ", tenant=" + tenantId);
        });

        String first = description
                .contextWrite(Context.of(
                        "traceId", "req-101",
                        "tenantId", "tenant-a"
                ))
                .block(Duration.ofSeconds(2));

        String second = description
                .contextWrite(Context.of(
                        "traceId", "req-202",
                        "tenantId", "tenant-b"
                ))
                .block(Duration.ofSeconds(2));

        System.out.println(first);
        System.out.println(second);

        // Flux.deferContextual reads Context when the subscriber subscribes.
        Flux<String> events = Flux.deferContextual(context -> {
            String requestId = context.getOrDefault(
                    "requestId", "anonymous"
            );
            return Flux.just("accepted", "completed")
                    .map(event -> requestId + ":" + event);
        });

        events.contextWrite(context ->
                context.put("requestId", "job-7")
        ).subscribe(System.out::println);
    }
}
```

From the directory containing `pom.xml`, with JDK 17+ and Maven installed, run:

```bash
mvn -q compile exec:java
```

Program stdout:

```text
trace=req-101, tenant=tenant-a
trace=req-202, tenant=tenant-b
job-7:accepted
job-7:completed
```

Explanation:

1. `description` is created once, but the `deferContextual` factory runs per subscription.
2. The first subscription has `traceId=req-101`, `tenantId=tenant-a`; the second subscription has its own values `req-202`, `tenant-b`.
3. The first subscription's Context does not overwrite or leak into the second subscription.
4. `events` reads `requestId` at subscribe time, then creates two elements carrying the same metadata.
5. `block(Duration)` appears only in `main()` of the console demo to obtain values for stdout; do not put this blocking wait into a WebFlux controller.

This example does not need Spring Boot; it uses Reactor Core's API directly. When run with synchronous cold sources, the stdout order above is deterministic.

## 10. Using Context in Spring WebFlux

### 10.1. Attaching a Correlation ID to the Pipeline

Suppose a filter extracts `X-Correlation-Id` from an HTTP request. You can attach the metadata to Context so appropriate downstream/upstream reactive layers can read it:

```java
// Illustrative code in a WebFlux application's WebFilter.
public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
    String correlationId = exchange.getRequest()
            .getHeaders()
            .getFirst("X-Correlation-Id");

    String safeId = correlationId == null
            ? UUID.randomUUID().toString()
            : correlationId;

    return chain.filter(exchange)
            .contextWrite(context ->
                    context.put("correlationId", safeId)
            );
}
```

This is **illustrative code** requiring Spring WebFlux imports and `java.util.UUID`; the `WebFilter` interface has a `filter` method returning `Mono<Void>`. `contextWrite` is attached to the Publisher returned by the filter so that Context can be read by upstream reactive components during request handling along the proper subscription boundary. When implementing a real filter, verify operator positions and how the framework composes the chain to ensure Context reaches the intended source.

Reading in a service:

```java
// Illustrative code in a reactive service.
Mono<Customer> findCustomer(long id) {
    return Mono.deferContextual(context -> {
        String correlationId = context.get("correlationId");
        return repository.findById(id)
                .doOnNext(customer ->
                        log.info("correlationId={} customer={}",
                                correlationId, customer.getId())
                );
    });
}
```

Here the service retrieves `correlationId` from Context and uses it in logging. The repository still returns `Mono<Customer>`; Context does not alter business data types.

### 10.2. Tenant Metadata

In a multi-tenant system, `tenantId` may be used by a repository/service to select a schema or add query predicates. Ensure the tenant is authenticated from a trusted source and that every query enforces proper isolation.

Do not allow clients to pass an arbitrary `tenantId` into Context and treat it as proof of authorization. Context is a transport mechanism for metadata inside the pipeline; it does not replace authentication/authorization, access checks, or anti-cross-tenant policies.

### 10.3. Spring Security and Reactive Transactions

Some frameworks integrate with Reactor Context to propagate `SecurityContext` or reactive transaction info. For Spring Security, use official integrations such as `ReactiveSecurityContextHolder` and official security configuration; never invent your own key and assume it replaces the standard security context.

For reactive transactions (e.g., R2DBC), Spring manages the transaction context within reactive execution. Keep the Publisher chain intact, avoiding `.block()` or detaching subscriptions arbitrarily inside a transaction, as doing so can break context/transaction boundaries. Never overwrite internal framework keys.

## 11. Keys, Data Types, and Information Safety

### 11.1. Choosing Stable Keys

The examples use String keys like `"traceId"` and `"tenantId"` for readability. In shared libraries, keys can collide with other libraries. You can use a constant object or a dedicated key type managed by the application:

```java
static final Object TENANT_KEY = new Object();

Mono<String> tenant = Mono.deferContextual(context ->
        Mono.just(context.get(TENANT_KEY))
).contextWrite(context -> context.put(TENANT_KEY, "tenant-a"));
```

If using a key class, ensure the same key instance or consistent equality rules when writing and reading.

### 11.2. Context Is Immutable, but Values Are Not Necessarily Immutable

Operations `put`, `delete`, and `putAll` create a new Context, but the object stored as a value may be mutable. If multiple operators hold the same mutable object, race conditions or unexpected state changes can still happen.

Prefer small, immutable values (`String`, IDs, immutable records, or unmodifiable metadata objects). Do not put a shared mutable `HashMap` into Context and turn it into a shared state store.

### 11.3. Do Not Store Secrets or Large Payloads Arbitrarily

Context can be accessed by many operators in the pipeline; it is not a private secret vault per layer. Avoid storing passwords, raw access tokens, payment card details, or sensitive personal data unless strictly necessary. Also avoid storing large objects, request bodies, or entity graphs in Context.

Put only the minimal metadata needed for propagation. If credentials are required, use dedicated security abstractions with controlled scope and lifecycle; do not log the entire Context.

### 11.4. Context Per Subscription, Not Global Per User

Do not use Context to store "the current user" in a static field or singleton. A server handles many concurrent requests; each subscription has its own Context. Reading via `deferContextual` preserves subscriber boundaries, whereas global mutable variables can leak data between requests.

## 12. Common Mistakes and Fixes

| Mistake | Why It Is Wrong | How to Fix |
|---|---|---|
| Calling `context.get("key")` when the key is not guaranteed to exist | Throws `NoSuchElementException`, emitting `onError` | Use `getOrDefault` or check `hasKey`; for required keys, fail intentionally |
| Using `defer()` and expecting the factory to read Context | `defer`'s Supplier does not receive `ContextView` | Use `deferContextual` |
| Placing `contextWrite` upstream of the operator that needs to read | Context flows from downstream to upstream; the key may not reach the reader | Place `contextWrite` downstream of the `deferContextual` section that needs to read |
| Treating Context like `ThreadLocal` | Threads may switch; libraries outside Reactor do not read Context automatically | Use `deferContextual` and appropriate context-propagation integrations |
| Assuming `contextWrite` mutates a shared Context | Context is immutable and per subscription | Return a new Context from `put`, do not share mutable state |
| Overwriting Spring Security/transaction keys | Can break security or transaction mechanisms | Use framework APIs and avoid internal keys |
| Using Context to hold entire requests/entities | Increases memory usage, hard to trace, hard to test | Store only small, necessary metadata |
| Calling `.block()` to read Context in a controller | Blocks the thread and breaks out of the reactive flow | Return the Publisher and read Context inside the chain |
| Expecting `ThreadLocal` MDC to sync automatically with Context | They are two independent mechanisms | Use version-appropriate logging/observability integrations |
| Calling `subscribe()` nested inside a service | Creates a separate subscription that can lose the caller's context/transaction | Return the Publisher for the caller to compose into the pipeline |

## 13. Testing Context with `StepVerifier`

If your project includes the `reactor-test` dependency, `StepVerifier` lets you test a subscriber's Context without `.block()`:

```java
import reactor.test.StepVerifier;
import reactor.util.context.Context;

Mono<String> trace = Mono.deferContextual(context ->
        Mono.just(context.get("traceId"))
);

StepVerifier.create(
        trace,
        StepVerifierOptions.create()
                .withInitialContext(Context.of("traceId", "test-123"))
)
.expectNext("test-123")
.verifyComplete();
```

This is a **test snippet**; it requires importing `reactor.test.StepVerifierOptions` and adding the `io.projectreactor:reactor-test` dependency in test scope. `withInitialContext` supplies the initial Context to the subscriber. `verifyComplete()` asserts one expected element and normal completion.

You can also test a Context missing a key:

```java
StepVerifier.create(trace)
        .expectError(java.util.NoSuchElementException.class)
        .verify();
```

And test separate Contexts per subscription:

```java
Mono<String> trace = Mono.deferContextual(context ->
        Mono.just(context.get("traceId"))
);

StepVerifier.create(
        trace,
        StepVerifierOptions.create()
                .withInitialContext(Context.of("traceId", "A"))
)
.expectNext("A")
.verifyComplete();

StepVerifier.create(
        trace,
        StepVerifierOptions.create()
                .withInitialContext(Context.of("traceId", "B"))
)
.expectNext("B")
.verifyComplete();
```

In real tests, verify required keys, defaults, key overrides, Context across `flatMap`/`publishOn`, and framework integrations. Do not test only a simple pipeline and assume every external library callback receives Context automatically.

## 14. Self-Check Exercises

**Q1.** What does `Mono.deferContextual(ctx -> Mono.just(ctx.get("traceId"))).contextWrite(ctx -> ctx.put("traceId", "r-1"))` emit?

**Answer:** `"r-1"`. `contextWrite` is downstream of `deferContextual` in declaration order and supplies the key to the upstream section.

**Q2.** Why can't `Mono.defer(() -> Mono.just("x"))` read `tenantId` directly from the factory?

**Answer:** `defer`'s Supplier does not receive a `ContextView`. Use `Mono.deferContextual(ctx -> ...)` if you need to read Context.

**Q3.** What does `context.get("userId")` do when the key is absent?

**Answer:** Throws `NoSuchElementException`, causing the `deferContextual` source to emit `onError`. Use `getOrDefault` if the key is truly optional.

**Q4.** If two subscribers subscribe to the same `Mono` variable with different Contexts, do they share the same `tenantId`?

**Answer:** No. Each subscription has its own Context; the same cold pipeline can read different values per subscriber.

**Q5.** Which direction does Context propagate compared to `onNext`?

**Answer:** Context propagates from the downstream subscriber back upstream; `onNext` data flows from upstream to downstream.

**Q6.** If `publishOn` switches threads, is Reactor Context automatically lost?

**Answer:** Reactor Context is propagated per subscription through Reactor operators, not bound to a thread. However, `ThreadLocal` and non-Reactor libraries require dedicated integration mechanisms.

**Q7.** Should you store raw access tokens or entire request bodies in Context?

**Answer:** No. Store only the minimal required metadata; use security abstractions and manage sensitive data within proper scopes.

## 15. Application Guidelines

- Use **`deferContextual`** when you need to read Context at subscription time and build a Publisher based on subscriber metadata.
- Use **`ContextView.get`** for required keys; use `getOrDefault` or `hasKey` for optional keys.
- Use **`contextWrite`** to add/replace metadata; remember Context is immutable and flows from downstream to upstream.
- Use Context for trace IDs, tenant metadata, and appropriate cross-layer info; primary business data should still be passed via parameters.
- Do not equate Context with `ThreadLocal`; do not assume arbitrary libraries outside Reactor can read Context automatically.
- Do not overwrite internal Spring Security/transaction keys; use official integration APIs.
- Test Context across operator, subscription, and scheduler boundaries with `StepVerifier` as needed.

**Remember:** `deferContextual` receives the `ContextView` of the **current subscription** to build the appropriate Publisher. Context propagates backward from downstream to upstream and is independent of threads; `contextWrite` is how you supply metadata, while `deferContextual` is how you read that metadata in a reactive pipeline.
