# Reactor Context: Propagation Direction and Operator Placement Effects

In Spring Reactive, a request can pass through a `WebFilter`, controller, service, repository, `WebClient`, and many Reactor operators. These layers sometimes need shared access to metadata across asynchronous execution: correlation ID, tenant ID, security info, or transaction state. Passing those values as parameters in every method can clutter API signatures. Relying on `ThreadLocal` as in synchronous programming is unsafe when the pipeline switches threads or multiple requests share an event-loop thread.

**Reactor Context** is an immutable key-value structure attached to a subscription's Subscriber. The most important rule is: **Context propagates backward from downstream to upstream when the subscription is established**, while data continues to flow forward from upstream to downstream. Therefore, the placement of **`contextWrite`** determines which operators can read a value. Placing **`contextWrite`** early in the code does not necessarily make the Context visible to operators placed after it.

This lesson is part of the **Reactor Context** topic, focusing on **context propagation direction and the effects of operator placement**.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain how Context is bound to the Subscriber and subscription rather than directly to a thread or individual item.
- Distinguish the propagation direction of **Context** from the propagation direction of **data signals**.
- Place **`contextWrite`**, **`deferContextual`**, and **`ContextView`** in the right positions.
- Predict the value read when multiple **`contextWrite`** calls write the same key.
- Understand how Context enters an inner publisher inside **`flatMap`** and how to write local Context inside a child branch.
- Avoid bugs caused by placing **`contextWrite`** upstream of the operator that needs to read it, calling **`subscribe()`** manually, or relying on `ThreadLocal`.
- Apply Context for correlation IDs, `WebFilter`, reactive security, and reactive transactions.
- Write a runnable Java 17+ program and test Context placement with `StepVerifier`.

## 2. What Is Context?

**Context** is Project Reactor's immutable key-value structure. It is attached to the Subscriber in a subscription and can be accessed by Reactor operators through **`ContextView`**.

Minimal example:

~~~java
Mono<String> greeting =
    Mono.deferContextual(ctx ->
        Mono.just("Hello " + ctx.get("name")))
    .contextWrite(ctx -> ctx.put("name", "Reactor"));
~~~

Upon subscription, **`contextWrite`** puts **`name=Reactor`** into the Context for upstream. **`deferContextual`** reads that value at subscription time and produces **`Hello Reactor`**.

Characteristics to remember:

- **Per subscription:** two subscribers to the same publisher can have different Contexts.
- **Immutable:** **`put`** and **`delete`** return a new Context; they do not mutate the old instance.
- **Read via `ContextView`:** reading operators typically receive a **`ContextView`**, not a modifiable Context.
- **Not `ThreadLocal`:** Context follows the subscription and works across scheduler boundaries of Reactor-native operators.
- **Not propagated over the network automatically:** when calling another service, you must transfer required metadata via HTTP headers, message headers, or the corresponding protocol.
- **Not a payload store:** keep metadata small and stable; avoid putting request bodies, large lists, or mutable application state into Context.

Context is not a global variable. It does not leak values across requests as long as each request creates its own subscription and writes Context within the proper scope.

## 3. Two Opposite Propagation Directions

Inside a pipeline, data and Context move in two opposite directions:

~~~text
                    Subscription / Context
                 <----------------------------
Source Publisher  ---> map ---> flatMap ---> Subscriber
                 ---------------------------->
                         onNext / onError / onComplete
                              Data signals
~~~

- **Data signals:** **`onNext`**, **`onError`**, and **`onComplete`** travel from the source (upstream) toward the subscriber (downstream).
- **Context:** when the subscriber subscribes, Context is requested from the downstream side and propagated backward upstream through the subscription.
- **`contextWrite`:** creates a new Context for operators positioned upstream of itself.
- **`deferContextual`:** reads the Context visible to its subscriber at subscription time.

A helpful mnemonic: **Context is read from downstream to upstream; data is processed from upstream to downstream**. Throughout this lesson, upstream is always closer to the source and downstream is closer to the subscriber.

### Why Is Context Bound to the Subscriber?

Reactive Streams passes a `Subscription` from Publisher to Subscriber. Reactor leverages subscription establishment to make the subscriber's Context available to upstream operators. Consequently, Context does not need to be packaged into every **`onNext`** as part of the payload. A sequence can emit thousands of items while each operator still reads the corresponding subscription's metadata.

## 4. `contextWrite` Only Affects Upstream

Consider this pipeline:

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just("source sees " + ctx.get("traceId")))
    .contextWrite(ctx -> ctx.put("traceId", "request-42"));
~~~

At subscription time, Context is written at **`contextWrite`**, then supplied to **`deferContextual`**. The result is **`source sees request-42`**.

Conversely:

~~~java
Mono<String> result = Mono.just("data")
    .contextWrite(ctx -> ctx.put("traceId", "request-42"))
    .flatMap(value ->
        Mono.deferContextual(ctx ->
            Mono.just("inner sees " +
                ctx.getOrDefault("traceId", "missing"))));
~~~

Here **`contextWrite`** sits **before `flatMap` in pipeline assembly order**. It only changes the Context seen by its own upstream. The subscriber of **`flatMap`** is downstream of **`contextWrite`**; the inner publisher created by **`flatMap`** inherits that subscriber's Context. Therefore, the inner publisher does not see **`request-42`** and the result is **`inner sees missing`**.

The fix is to place **`contextWrite`** downstream of **`flatMap`**:

~~~java
Mono<String> result = Mono.just("data")
    .flatMap(value ->
        Mono.deferContextual(ctx ->
            Mono.just("inner sees " +
                ctx.getOrDefault("traceId", "missing"))))
    .contextWrite(ctx -> ctx.put("traceId", "request-42"));
~~~

Now Context is supplied to the subscriber of **`flatMap`**, so the inner publisher inherits **`traceId=request-42`**.

**Practical rule:** place **`contextWrite`** after (downstream of) the part of the pipeline that needs to read Context. If you need to pass values into a source-like operator such as **`deferContextual`**, place **`contextWrite`** at the end of that chain.

## 5. Multiple `contextWrite` Calls Writing the Same Key

Context propagates backward from the end of the pipeline to the beginning. When the same key is written multiple times, the reading operator sees the last value it receives along the Context path — typically the value written in the **`contextWrite`** closer to the source in the chain.

Example:

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just(ctx.get("message")))
    .contextWrite(ctx -> ctx.put("message", "Reactor"))
    .contextWrite(ctx -> ctx.put("message", "World"));
~~~

The result is **`Reactor`**, not **`World`**.

Sequence at subscription time:

1. The Subscriber starts with an empty Context.
2. **`contextWrite`** at the end of the pipeline writes **`message=World`**.
3. Subscription continues upstream; the **`contextWrite`** closer to the source receives that Context and overwrites it to **`message=Reactor`**.
4. **`deferContextual`** reads **`message=Reactor`**.

~~~text
Subscriber Context={}
       |
       v
contextWrite("World")       Context={message: World}
       |
       v
contextWrite("Reactor")     Context={message: Reactor}
       |
       v
deferContextual             reads "Reactor"
~~~

This matters when multiple layers set metadata such as **`tenantId`**, **`traceId`**, or **`locale`**. Establish clear conventions about which layer is allowed to override a key. Never assume "written later in code" always wins: subscription traverses operators in the opposite direction of data flow.

### Using a Prebuilt Context and Updating Context

You can provide an already-created Context:

~~~java
.contextWrite(Context.of("traceId", "trace-123"))
~~~

Or update with a function:

~~~java
.contextWrite(ctx -> ctx.put("traceId", "trace-123"))
~~~

**`Context.of`** fits creating a small Context with known key-value pairs. The functional **`contextWrite`** is useful when you want to keep existing keys and add/delete a key:

~~~java
.contextWrite(ctx -> ctx
    .put("tenantId", "tenant-7")
    .put("traceId", "trace-123")
    .delete("temporaryKey"))
~~~

Because Context is immutable, you must **return** the result of **`put`** or **`delete`**. The snippet below is wrong because it discards the new Context:

~~~java
.contextWrite(ctx -> {
    ctx.put("traceId", "trace-123"); // result discarded
    return ctx;
})
~~~

## 6. `deferContextual`: Reading Context at the Right Time

**`Mono.deferContextual`** receives a **`ContextView`** when a subscriber subscribes. It fits when a publisher needs to read metadata to construct the next operation:

~~~java
Mono<String> message = Mono.deferContextual(ctx -> {
    String traceId = ctx.getOrDefault("traceId", "no-trace");
    return Mono.just("processing " + traceId);
});
~~~

If you call **`ctx.get("traceId")`** when the key does not exist, Reactor throws an error because the key cannot be found. When a value may be absent, use:

- **`ctx.hasKey("traceId")`** to check existence.
- **`ctx.getOrDefault("traceId", "no-trace")`** to get a default value.
- **`ctx.getOrEmpty("traceId")`** if you want to work with `Optional`.

**`ContextView`** is a read-only interface. If you need to change Context, use **`contextWrite`**; do not try to cast `ContextView` and mutate it.

### Reading Context Mid-Pipeline

When you need to read Context somewhere other than the source, Reactor offers **`transformDeferredContextual`**:

~~~java
Flux<String> result = Flux.just("a", "b")
    .transformDeferredContextual((values, ctx) ->
        values.map(value ->
            value + "-" + ctx.getOrDefault("tenant", "public")))
    .contextWrite(ctx -> ctx.put("tenant", "tenant-7"));
~~~

**`transformDeferredContextual`** receives the publisher at that operator position and the `ContextView` visible to the subscriber at that position. It is helpful for libraries or reusable operators that need to combine both the data stream and metadata. For simple logic at a source or inner publisher, **`deferContextual`** is usually easier to read.

## 7. Context Inside `flatMap` and Child Publishers

A subtle point is that the inner publisher inside **`flatMap`** receives its Context from the subscriber of **`flatMap`**. Context written downstream of **`flatMap`** can be read by the inner publisher. Context written inside an inner publisher is scoped only to that inner publisher and does not automatically modify the main chain's Context.

Example:

~~~java
Mono<String> result = Mono.just("Hello")
    .flatMap(value ->
        Mono.deferContextual(ctx ->
            Mono.just(value + " " + ctx.get("message"))))
    .flatMap(value ->
        Mono.deferContextual(ctx ->
            Mono.just(value + " " + ctx.get("message")))
            .contextWrite(ctx -> ctx.put("message", "Reactor")))
    .contextWrite(ctx -> ctx.put("message", "World"));
~~~

The result is **`Hello World Reactor`**.

Explanation:

1. The final **`contextWrite`** sets **`message=World`** for the main chain.
2. The first **`flatMap`** inner publisher inherits the main Context, so it reads **`World`**.
3. The second **`flatMap`** inner publisher has a local **`contextWrite`**, so it reads **`Reactor`**.
4. Writing **`Reactor`** does not alter the main Context; it applies only upstream within that inner publisher.

~~~text
Main sequence Context: {message: World}
      |
      +-- flatMap #1 inner reads World
      |
      +-- flatMap #2 inner own Context:
             contextWrite(message=Reactor)
             deferContextual reads Reactor
~~~

This allows a library to create a local Context for a child call without leaking values to other branches. Conversely, if you want a key to apply to all inner publishers, place Context downstream of the operator creating the inner publishers, not only inside one child source.

### Multiple Independent Inner Publishers

If **`flatMap`** spawns multiple branches, each branch can inherit the main subscription's Context. A **`contextWrite`** placed inside one branch affects only that branch. Never use Context to share mutable state across branches; if multiple branches update a mutable object stored in Context, race conditions still happen as usual.

## 8. How Does Context Differ from `ThreadLocal`?

**`ThreadLocal`** stores values per thread. In WebFlux, a single request can pass across multiple threads or schedulers; multiple requests can also share a single event-loop thread at different times. Therefore, reading **`ThreadLocal`** directly is not a reliable way to carry metadata across an asynchronous pipeline.

| Criterion | Reactor Context | `ThreadLocal` |
| --- | --- | --- |
| Bound to | Subscriber/subscription | Thread |
| Propagation | Via Reactor's Context mechanism | Via the current thread |
| Across `publishOn`/`subscribeOn` | Reactor Context continues to be passed by Reactor operators per subscriber | `ThreadLocal` does not automatically follow thread switches |
| Reading | `deferContextual`, `transformDeferredContextual` | `ThreadLocal.get()` |
| Suitable for | Metadata of a reactive flow | Synchronous state bound to one thread |
| Lifecycle | Tied to the subscription and configured Context | Must manually manage `set`/`remove` |

Do not read this table as saying **`ThreadLocal`** is always wrong. It remains useful in synchronous code and legacy libraries. The point is **never assume `ThreadLocal` will be preserved in a reactive pipeline**.

### MDC and Logging

SLF4J MDC is usually backed by `ThreadLocal`. If you want to log **`traceId`** in a reactive application:

1. Store trace/correlation IDs in Reactor Context.
2. Use Spring and Micrometer's tracing/observability integrations whenever possible.
3. If you need to bridge Context to `ThreadLocal`/MDC, use a context-propagation mechanism configured and tested for your Reactor/Micrometer versions.
4. Never set MDC manually in an operator and forget to clear it; the thread can be reused for another request.

**`Hooks.enableAutomaticContextPropagation()`** and related integrations are version-dependent configuration features; do not enable a global hook just to get a trace ID into one log without evaluating its impact. In business code, prefer reading Context directly or using integrated tracing APIs.

## 9. Context Across Schedulers and Asynchronous Boundaries

**`subscribeOn`** and **`publishOn`** change where part of a pipeline executes. They do not turn Context into `ThreadLocal`. Context is bound to the subscription, so Reactor-native operators can still access it after switching schedulers.

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.delay(Duration.ofMillis(10))
            .map(ignored ->
                "trace=" + ctx.get("traceId")))
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .contextWrite(ctx -> ctx.put("traceId", "trace-99"));
~~~

Upon subscription, **`traceId`** can still be read after the asynchronous step. **`ContextView`** is obtained inside **`deferContextual`** and captured in the lambda; there is no need to read a `ThreadLocal` on another thread.

Two caveats:

- Context is propagated automatically only through operators integrated with Reactor. If you invoke a callback library outside Reactor or create an independent subscription, you must use an appropriate bridge/API.
- Calling **`subscribe()`** nested inside **`map`/`flatMap`** creates a new subscriber. That new subscriber does not automatically inherit the parent pipeline's Context. Compose publishers and return the result to the main chain.

## 10. Context Is Per Subscription, Not Per Publisher Object

A single publisher can be reused many times with different Contexts:

~~~java
Mono<String> trace = Mono.deferContextual(ctx ->
    Mono.just(ctx.getOrDefault("traceId", "missing")));

String first = trace
    .contextWrite(Context.of("traceId", "request-A"))
    .block();

String second = trace
    .contextWrite(Context.of("traceId", "request-B"))
    .block();
~~~

The results are **`request-A`** and **`request-B`**. The publisher is constructed once, while each **`block()`** creates a separate subscription and a separate Context. **`block()`** here is solely for illustrating in a console program; never use **`block()`** in a WebFlux handler.

### Be Careful with `cache`

**`cache()`** can share emitted signals across multiple subscribers. If a publisher produces Context-dependent results, do not assume every subscriber gets its own result after the cache is populated. For example, a publisher that reads **`tenantId`** and caches the result can violate tenant isolation if one cache instance is shared. Design cache keys to include tenant/identity or place caching at an appropriate boundary; do not use Context to mask an incomplete cache key.

### Context Does Not Automatically Cross to Other Processes

When calling `WebClient`, Reactor Context does not automatically turn into HTTP headers on the wire. You must extract trace/correlation metadata and add it to headers per protocol, or use a tracing integration that supports propagation. Likewise, sending messages to a broker requires putting necessary metadata into message headers. The receiving process builds a new Context from the received metadata and applies its own authentication/authorization rules.

## 11. Applying in Spring WebFlux with `WebFilter`

A **`WebFilter`** can attach a request ID to Context for the entire request pipeline:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.WebFilter;

@Configuration
public class RequestContextConfiguration {

    public static final String TRACE_ID = "traceId";

    @Bean
    WebFilter requestContextFilter() {
        return (exchange, chain) ->
            chain.filter(exchange)
                .contextWrite(ctx ->
                    ctx.put(TRACE_ID, exchange.getRequest().getId()));
    }
}
~~~

This is integration code in a Spring WebFlux application; it requires the WebFlux dependency and component scan configuration. **`exchange.getRequest().getId()`** is the server-assigned request ID. If the application accepts a correlation ID from clients, validate length/characters and explicitly decide which source to trust before writing it into Context.

A service can read Context at processing time:

~~~java
import reactor.core.publisher.Mono;

public class ProfileService {

    private final ProfileRepository repository;

    public ProfileService(ProfileRepository repository) {
        this.repository = repository;
    }

    public Mono<Profile> findById(String id) {
        return Mono.deferContextual(ctx -> {
            String traceId = ctx.getOrDefault(
                RequestContextConfiguration.TRACE_ID, "no-trace");

            return repository.findById(id)
                .doOnNext(profile ->
                    log.info("traceId={} profileLoaded={}",
                        traceId, profile.id()));
        });
    }
}
~~~

This is an illustrative fragment requiring declarations for **`Profile`**, **`ProfileRepository`**, and a logger. In real projects, you do not have to pass the request ID through every method parameter; Context lets reactive services or libraries read metadata at the right boundaries.

### Spring Security and Reactive Transactions

Spring Security uses Reactor Context to hold **`SecurityContext`** during reactive execution; **`ReactiveSecurityContextHolder.getContext()`** returns a publisher to read security information. Never put an arbitrary authentication object into Context to bypass the framework's authentication/authorization flow.

Reactive transaction management also binds transaction state to Reactor Context via **`ReactiveTransactionManager`/`TransactionalOperator`**. As a result, a reactive transaction can continue across threads without relying on synchronous thread-bound `ThreadLocal` transactions. Never call **`subscribe()`** detached from the transaction pipeline; doing so can create a subscription outside the intended transaction scope.

## 12. Runnable Java 17+ Example: Observing Context Placement

Create a Maven project:

~~~text
reactor-context-position/
├── pom.xml
├── src/main/java/ContextPositionDemo.java
└── src/test/java/ContextPositionTest.java
~~~

Contents of **`pom.xml`**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>reactor-context-position</artifactId>
  <version>1.0-SNAPSHOT</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core</artifactId>
      <version>3.6.9</version>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <version>3.6.9</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.10.3</version>
      <scope>test</scope>
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
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
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

Contents of **`src/main/java/ContextPositionDemo.java`**:

~~~java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

public class ContextPositionDemo {

    private static Mono<String> readTrace() {
        return Mono.deferContextual(ctx ->
            Mono.just("source sees " +
                ctx.getOrDefault("traceId", "missing")));
    }

    public static void main(String[] args) {
        String precedence = readTrace()
            .contextWrite(ctx -> ctx.put("traceId", "near-source"))
            .contextWrite(ctx -> ctx.put("traceId", "near-subscriber"))
            .block();

        Mono<String> visibleToInner = Mono.just("item")
            .flatMap(value -> Mono.deferContextual(ctx ->
                Mono.just("inner sees " +
                    ctx.getOrDefault("traceId", "missing"))))
            .contextWrite(Context.of("traceId", "request-42"));

        Mono<String> misplaced = Mono.just("item")
            .contextWrite(Context.of("traceId", "upstream-only"))
            .flatMap(value -> Mono.deferContextual(ctx ->
                Mono.just("inner sees " +
                    ctx.getOrDefault("traceId", "missing"))));

        System.out.println(precedence);
        System.out.println(visibleToInner.block());
        System.out.println(misplaced.block());
    }
}
~~~

Run from the project directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=ContextPositionDemo
~~~

Stdout:

~~~text
source sees near-source
inner sees request-42
inner sees missing
~~~

Explanation:

1. **`near-subscriber`** is written first as subscription moves upstream; **`near-source`** is written closer to the source and overwrites the same key, so the source sees **`near-source`**.
2. **`contextWrite`** at the end of the second chain provides Context to the subscriber of **`flatMap`**; the inner publisher inherits **`request-42`**.
3. **`contextWrite`** before **`flatMap`** affects only its own upstream; the subscriber of **`flatMap`** does not receive that key, so the inner publisher sees **`missing`**.

**`block()`** appears only in **`main`** to print demo results. In a WebFlux application, return **`Mono`/`Flux`** and let the framework manage subscriptions.

## 13. Testing Context Placement with `StepVerifier`

In the Maven project above, create **`src/test/java/ContextPositionTest.java`**:

~~~java
import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.util.context.Context;

class ContextPositionTest {

    @Test
    void subscriberInitialContextIsVisibleUpstream() {
        Mono<String> source = Mono.deferContextual(ctx ->
            Mono.just(ctx.get("traceId")));

        StepVerifier.create(
                source,
                StepVerifierOptions.create()
                    .withInitialContext(Context.of("traceId", "test-123")))
            .expectNext("test-123")
            .verifyComplete();
    }

    @Test
    void contextWriteAfterFlatMapIsVisibleToInner() {
        Mono<String> source = Mono.just("item")
            .flatMap(value -> Mono.deferContextual(ctx ->
                Mono.just(ctx.getOrDefault("traceId", "missing"))))
            .contextWrite(Context.of("traceId", "visible"));

        StepVerifier.create(source)
            .expectNext("visible")
            .verifyComplete();
    }

    @Test
    void contextWriteBeforeFlatMapIsNotVisibleToItsInner() {
        Mono<String> source = Mono.just("item")
            .contextWrite(Context.of("traceId", "upstream-only"))
            .flatMap(value -> Mono.deferContextual(ctx ->
                Mono.just(ctx.getOrDefault("traceId", "missing"))));

        StepVerifier.create(source)
            .expectNext("missing")
            .verifyComplete();
    }

    @Test
    void innerContextWriteIsScopedToThatInner() {
        Mono<String> source = Mono.just("item")
            .flatMap(value -> Mono.deferContextual(ctx ->
                Mono.just(ctx.get("traceId")))
                .contextWrite(ctx -> ctx.put("traceId", "inner")))
            .contextWrite(ctx -> ctx.put("traceId", "outer"));

        StepVerifier.create(source)
            .expectNext("inner")
            .verifyComplete();
    }
}
~~~

Run:

~~~bash
mvn -q test
~~~

Maven exits with code 0 when all four tests pass. The tests verify **that Context is visible at specific positions**, rather than merely checking that the pipeline returns a string. This is especially important because a misplaced **`contextWrite`** can still run successfully while silently using default values or missing metadata.

## 14. Common Mistakes and Fixes

1. **Placing `contextWrite` before the operator that needs to read it:** the key is only supplied to its upstream. Place Context downstream of the consumer that needs to read it.
2. **Thinking Context travels with every `onNext`:** Context is bound to the subscriber/subscription, not the payload.
3. **Confusing Context with `ThreadLocal`:** Context follows the Reactor chain; `ThreadLocal` follows the thread.
4. **Forgetting immutability:** `ctx.put(...)` returns a new Context. If you do not return the result, the key is not added.
5. **Using `get` for optional keys:** can throw an error when the key is missing; use `getOrDefault` or `hasKey`.
6. **Writing the same key in multiple layers without a convention:** the value closer to the source can overwrite a value previously set further downstream.
7. **Thinking an inner `flatMap` automatically shares changes outward:** Context written inside an inner publisher is isolated to that inner publisher's scope.
8. **Calling nested `subscribe()` manually:** creates an independent subscription that does not automatically inherit the parent pipeline's Context and lifecycle. Compose publishers instead.
9. **Storing large mutable objects in Context:** branches can share references, causing race conditions and prolonged memory retention.
10. **Putting sensitive data into Context and logging the whole thing:** store only necessary metadata; avoid logging tokens, credentials, or personal data.
11. **Assuming Context propagates automatically across `WebClient`/brokers:** transfer metadata to HTTP/message headers or use a tracing integration.
12. **Using `cache` for tenant-dependent results without tenant in the cache key:** another subscriber may receive the previous subscriber's cached result.
13. **Blaming `publishOn` for Context disappearing:** Reactor-native operators preserve Context per subscriber; if data is lost in an external library, a suitable bridge is needed.
14. **Using Context instead of business parameters:** data required to understand or control a function's result belongs in the API; Context is for cross-cutting metadata.
15. **Modifying `SecurityContext` in Context manually:** use reactive Spring Security APIs and preserve the authentication/authorization flow.
16. **Enabling automatic context propagation without understanding its impact:** configure `ThreadLocal`/MDC bridging per version, measure, and test before enabling application-wide.

## 15. Checklist When Designing Context

Before adding a key to Reactor Context, determine:

- **Purpose:** is this cross-cutting metadata like a trace ID, tenant, or security context, or is it actually business data that should be passed as a parameter?
- **Who writes the key?** `WebFilter`, adapter, service, or library? Is there one clear owner?
- **Who reads the key?** Where is the reading operator positioned relative to `contextWrite`?
- **Scope:** is the key needed for the whole pipeline, an inner publisher, or a sub-request?
- **Default:** can the key be absent? Do you need `getOrDefault`, `hasKey`, or fail-fast?
- **Key collisions:** could multiple layers write the same key and overwrite each other? Are namespaces/key constants clear?
- **Concurrency:** are any mutable objects placed into Context and shared across branches?
- **Threads:** are there any `ThreadLocal`/MDC usages or callback libraries outside Reactor?
- **Process boundaries:** which metadata must be transferred via HTTP headers or message headers?
- **Caching:** do Context-dependent results get cached and shared across subscribers?
- **Security:** does the key hold sensitive data or can it be spoofed by clients?
- **Lifecycle:** are there nested `subscribe()` calls, caches, or long-lived publishers that keep Context alive longer than expected?

## 16. Self-Check Exercises

**Exercise 1.** Why can **`Mono.deferContextual(...).contextWrite(...)`** normally read the key?  
**Answer:** As subscription flows from downstream to upstream, **`contextWrite`** provides the Context to the source-like operator **`deferContextual`**.

**Exercise 2.** Does **`Mono.just("x").contextWrite(put("id","A")).flatMap(v -> Mono.deferContextual(...))`** guarantee the inner publisher sees `A`?  
**Answer:** No. **`contextWrite`** is upstream of **`flatMap`**; the inner publisher inherits the Context of **`flatMap`**'s subscriber, not a Context meant only for the source before it.

**Exercise 3.** If two **`contextWrite`** calls write the same key, which value does **`deferContextual`** see?  
**Answer:** The value from the write closer to the source along the subscription path, because Context propagates from downstream to upstream and the subsequent write during propagation overwrites it.

**Exercise 4.** An inner publisher writes **`tenant=inner`** into Context. Does another branch of the same **`flatMap`** automatically see **`tenant=inner`**?  
**Answer:** No. Context written inside an inner publisher is scoped only to that branch; it does not mutate the Context of the main sequence or sibling inner publishers.

**Exercise 5.** **`publishOn`** switches threads. Does Context disappear?  
**Answer:** Not for Reactor-native operators; Context is bound to the subscription, not to a thread. `ThreadLocal`, however, is not automatically preserved.

**Exercise 6.** Should you store the entire request object in Context so every service can read it?  
**Answer:** Generally no. Context should hold small, stable metadata; business data should be passed via appropriate APIs/DTOs.

**Exercise 7.** `WebClient` calls another service. Does the **`traceId`** Context in the current application automatically appear on the remote server?  
**Answer:** Not automatically. It must be propagated via HTTP headers or a tracing integration.

**Exercise 8.** Why is nested **`subscribe()`** dangerous for Context?  
**Answer:** It creates a separate subscription, detached from the parent chain's subscriber/lifecycle; Context and cancellation are not automatically inherited as intended.

**Exercise 9.** A publisher depending on **`tenantId`** is cached and used for multiple tenants. What needs attention?  
**Answer:** Caching can share results across subscribers; the cache key and cache scope must include the tenant, or the publisher must be separated per tenant.

**Exercise 10.** Why does calling **`ctx.put("traceId","x")`** inside a lambda while returning **`ctx`** have no effect?  
**Answer:** Context is immutable; **`put`** creates a new Context. You must return the new Context or write **`ctx -> ctx.put(...)`**.

## 17. Takeaway

Reactor Context is metadata **bound to the Subscriber**, established at subscription time and propagated **from downstream to upstream**. Data continues to flow from upstream to downstream. **`contextWrite`** supplies Context to everything upstream of it; **`deferContextual`** reads Context at the corresponding subscriber position. Therefore, **operator placement is part of the semantics**, not merely a code formatting detail.

When using Context with **`flatMap`**, the inner publisher inherits the Context of the subscriber creating the branch; Context written inside an inner publisher affects only that branch. Context works across Reactor schedulers without relying on `ThreadLocal`, but it does not automatically cross process boundaries or independent subscriptions. Keep Context small, immutable, clearly keyed, and test placement with `StepVerifier` to prevent silent metadata bugs.

### References

- Project Reactor, [Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html).
- Project Reactor, [Context API](https://projectreactor.io/docs/core/release/api/reactor/util/context/Context.html) and [ContextView API](https://projectreactor.io/docs/core/release/api/reactor/util/context/ContextView.html).
- Project Reactor, [StepVerifier and testing](https://projectreactor.io/docs/core/release/reference/testing.html).
- Spring Framework, [WebFlux Filters](https://docs.spring.io/spring-framework/reference/web/webflux/filters.html).
- Spring Security, [Reactive Security Context](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html).
