# Testing Reactor Context with StepVerifier in Spring Framework Reactive

## 1. Why Test `Context`?

In a Spring WebFlux application, a `Mono` or `Flux` does not merely transmit data signals (`onNext`, `onError`, `onComplete`). Each subscription can also carry a **Reactor Context**: a small key–value store holding metadata attached to the processing flow, such as a correlation ID, tenant ID, trace information, or Spring Security context.

Unlike arguments passed via `onNext`, these values are **not core business data**. They describe a subscriber's context and propagate via Reactor's subscription mechanism.

When testing a pipeline, writing only:

```java
StepVerifier.create(service.find("42"))
        .expectNextMatches(item -> item.id().equals("42"))
        .verifyComplete();
```

is insufficient if the service also depends on a tenant, request ID, or identity inside Reactor Context. A response might look right in a simple setup yet fail when:

- The tenant is lost after an operator or nested publisher.
- Two concurrent requests accidentally mix up each other's context.
- `contextWrite` is placed in the wrong position so an operator never sees the key.
- `ThreadLocal` loses its value when switching threads.
- Fallback logic masks a missing mandatory context key.
- Tests only assert `onNext` without verifying the context actually reached the source.

This lesson walks through **testing Reactor Context with `StepVerifier`**: from the Context propagation model, `StepVerifierOptions.withInitialContext(...)`, and `expectAccessibleContext()`, to tricky scenarios involving `contextWrite` ordering, async boundaries, Reactor Context in Spring Security, and a Java 17+ test suite runnable with Maven.

**Desired outcome:** write tests that verify both Publisher signals and the exact subscription context; detect lost Context or cross-request context bleed without abusing `block()`, `ThreadLocal`, or global state.

## 2. `Context` and `ContextView`: Nature of the Data

The APIs live in the package:

```java
import reactor.util.context.Context;
import reactor.util.context.ContextView;
```

`Context` is an immutable key–value store optimized for small metadata payloads. `ContextView` is the read-only interface.

| API | Effect |
|---|---|
| `Context.empty()` | Creates an empty context |
| `Context.of(key, value)` | Creates a context with key–value pairs |
| `context.put(key, value)` | Returns a **new Context** with the key added/overwritten |
| `context.delete(key)` | Returns a new Context without a key |
| `context.putAll(other)` | Returns a new Context with merged entries |
| `view.hasKey(key)` | Checks whether the key exists |
| `view.get(key)` | Gets value; throws if key is missing |
| `view.getOrDefault(key, defaultValue)` | Gets value or fallback |
| `view.getOrEmpty(key)` | Gets an `Optional<T>` |
| `view.size()` | Counts key–value pairs |
| `view.stream()` | Streams entries |

Example:

```java
Context original = Context.of("tenant", "alpha");
Context updated = original.put("traceId", "trace-17");

System.out.println(original.hasKey("traceId")); // false
System.out.println(updated.hasKey("traceId"));  // true
```

`original` is never mutated. This property keeps contexts isolated across subscribers.

### 2.1. Do Not Confuse Reactor Context with Other Concepts

- `reactor.util.context.Context`: subscription-scoped metadata.
- `org.springframework.context.ApplicationContext`: Spring's bean container.
- `ServerWebExchange`: HTTP request/response in WebFlux.
- `SecurityContext`: Spring Security authentication/authorization data.
- `ThreadLocal`: thread-bound state that does not automatically follow a subscription across schedulers.

A `SecurityContext` can be stored inside Reactor Context via `ReactiveSecurityContextHolder`, yet the two Context types are not identical.

### 2.2. What Should and Should Not Go into Reactor Context

Appropriate:

- Correlation ID or trace ID.
- Verified tenant identifier.
- Security context created by Spring Security.
- Small metadata for tracing, logging, or authorization libraries.

Inappropriate:

- Lists of millions of records.
- Large mutable state shared across requests.
- A connection or file resource needing its own lifecycle management.
- Raw passwords or tokens logged indiscriminately.
- Large business payloads that belong in `Mono<T>`/`Flux<T>`.

`Context` is structurally immutable, yet value objects stored inside it can be mutable. Do not interpret "immutable Context" as "every value inside is automatically thread-safe".

## 3. Context Belongs to the Subscriber, Not the Publisher Variable

A single Publisher can be subscribed to many times. Each subscription can carry a different Context.

```text
                Shared Mono<String>
                    |
             Mono.deferContextual(...)
                    ^
                    |
           Subscription propagation
              /              \
             /                \
     Subscriber A          Subscriber B
     Context tenant=A      Context tenant=B
             |                |
         "A:hello"         "B:hello"
```

Therefore, never store a `currentTenant` field in a singleton service and mutate it per request. A `@Service` can serve thousands of concurrent requests simultaneously, whereas Reactor Context travels with each subscription.

### 3.1. Context Propagates Along the Subscription Direction

A helpful mental model:

```text
assembly:       source --- map --- flatMap --- contextWrite --- subscriber
data signals:   onNext --------------------------------------->

Context:        source <--------------------------------------- subscriber
                               contextWrite adds key
```

Data signals flow from source to downstream. Context is observed in the opposite direction, from subscriber upstream during subscription setup.

This explains why the placement of `contextWrite` determines which operators see a key.

### 3.2. Assembly vs. Subscription

Example:

```java
Mono<String> source = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("tenant", "public")));
```

Constructing the Publisher does not read Context yet. The lambda inside `deferContextual` runs when a subscription occurs, at which point `ContextView` is supplied.

If you read a tenant from a global variable **before** creating the Publisher, each subscriber loses its chance to have an independent context.

## 4. Writing and Reading Context with `contextWrite` and `deferContextual`

### 4.1. Writing Context

```java
Mono<String> result = Mono.deferContextual(ctx ->
                Mono.just("tenant=" + ctx.get("tenant")))
        .contextWrite(Context.of("tenant", "alpha"));
```

Expected value:

```text
tenant=alpha
```

`contextWrite(ContextView)` merges the supplied entries into the Context coming from downstream and produces a new Context for upstream. You can also use the function overload:

```java
.contextWrite(ctx -> ctx.put("tenant", "alpha"))
```

Context is never mutated in place. `put(...)` returns a new Context.

### 4.2. Reading Context Safely

```java
Mono<String> tenant = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("tenant", "public")));
```

Here a missing key does not break the request because the contract permits a default `"public"` tenant.

Conversely, if tenant is **mandatory**, fail explicitly:

```java
Mono<String> tenantRequired = Mono.deferContextual(ctx -> {
    if (!ctx.hasKey("tenant")) {
        return Mono.error(
                new IllegalStateException("tenant missing"));
    }

    String tenantId = ctx.get("tenant");
    return Mono.just(tenantId);
});
```

Never attach a `"public"` fallback to operations requiring strict tenant isolation. A convenient fallback can turn into a severe authorization vulnerability.

### 4.3. `ContextView` Separates Reading from Writing

A library that only reads Context should accept `ContextView` rather than requiring write capabilities:

```java
private String resolveTenant(ContextView context) {
    return context.getOrDefault("tenant", "public");
}
```

Read APIs should ask only for what they use. Context writes generally belong at boundaries like `WebFilter`, adapters, clients, or test subscribers.

## 5. `StepVerifier`: Testing Both Signals and Context

`StepVerifier` lives in the `reactor-test` artifact, usually declared in `test` scope:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
```

Simple test:

```java
StepVerifier.create(Mono.just("ok"))
        .expectNext("ok")
        .verifyComplete();
```

To supply Context to the subscriber, create `StepVerifierOptions`:

```java
StepVerifierOptions options = StepVerifierOptions.create()
        .withInitialContext(Context.of("tenant", "alpha"));

StepVerifier.create(
                Mono.deferContextual(ctx ->
                        Mono.just(ctx.get("tenant"))),
                options)
        .expectNext("alpha")
        .verifyComplete();
```

`withInitialContext` sets the initial Context on **`StepVerifier`'s subscriber**, without mutating a global variable, writing to a static map, or calling `block()`.

### 5.1. `StepVerifierOptions` APIs

| API | Purpose |
|---|---|
| `create()` | Creates options |
| `withInitialContext(Context)` | Attaches Context to the test subscriber |
| `scenarioName(String)` | Names the scenario for assertion diagnostics |
| `initialRequest(long)` | Controls initial demand when testing backpressure |
| `checkUnderRequesting(boolean)` | Configures under-requesting checks |
| `copy()` | Copies options |

Example:

```java
StepVerifierOptions options = StepVerifierOptions.create()
        .scenarioName("tenant-aware greeting")
        .withInitialContext(Context.of(
                "tenant", "alpha",
                "traceId", "req-17"));
```

When a test fails, `scenarioName` helps identify which case broke. Avoid putting tokens or personal data into scenario names.

### 5.2. Testing Context and Output in the Same Test

```java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just(ctx.get("tenant")));

StepVerifier.create(
                result,
                StepVerifierOptions.create()
                        .withInitialContext(
                                Context.of("tenant", "alpha")))
        .expectAccessibleContext()
        .contains("tenant", "alpha")
        .then()
        .expectNext("alpha")
        .verifyComplete();
```

The test verifies **two independent facts**:

1. Context propagated to the inspection point during the subscription phase and contains `"tenant"="alpha"`.
2. The Publisher emitted `"alpha"` and completed.

Checking output alone could miss a pipeline that accidentally hardcodes `"alpha"`. Checking Context alone without checking output could miss logic reading the wrong key.

## 6. `expectAccessibleContext()` and `ContextExpectations`

After calling:

```java
.expectAccessibleContext()
```

`StepVerifier` transitions to `StepVerifier.ContextExpectations<T>` to declare assertions on the Context propagated during the subscription phase.

Key APIs:

| API | Meaning |
|---|---|
| `.hasKey("tenant")` | Requires the key to be present |
| `.contains("tenant", "alpha")` | Requires the key to have the exact value |
| `.containsAllOf(Context.of(...))` | Requires containing all specified key–value pairs |
| `.containsOnly(Context.of(...))` | Requires exact pairs with no extra entries |
| `.hasSize(2)` | Requires Context to have exactly 2 entries |
| `.matches(predicate)` | Checks a custom predicate |
| `.matches(predicate, description)` | Predicate with failure description |
| `.assertThat(consumer)` | Runs custom assertions |
| `.then()` | Returns to verifying Publisher signals |

### 6.1. Checking Key–Value Pairs

```java
StepVerifier.create(
                Mono.just(5),
                StepVerifierOptions.create()
                        .withInitialContext(
                                Context.of("tenant", "alpha", "traceId", "t-1")))
        .expectAccessibleContext()
        .contains("tenant", "alpha")
        .hasKey("traceId")
        .hasSize(2)
        .then()
        .expectNext(5)
        .verifyComplete();
```

Avoid using `.containsOnly(...)` or `.hasSize(...)` rigidly in full WebFlux applications, since tracing/security libraries may add their own Context entries. Focusing assertions on **the keys owned by your code** produces less brittle tests.

### 6.2. Custom Predicate

```java
StepVerifier.create(
                Mono.just("ready"),
                StepVerifierOptions.create()
                        .withInitialContext(
                                Context.of("traceId", "req-abc")))
        .expectAccessibleContext()
        .matches(
                ctx -> ctx.<String>get("traceId").startsWith("req-"),
                "traceId must start with req-")
        .then()
        .expectNext("ready")
        .verifyComplete();
```

Use `.matches(...)` for conditions cleanly expressed as a predicate. If you need multiple assertions with individual failure messages, use `.assertThat(...)`.

### 6.3. Custom Assertions

```java
StepVerifier.create(
                Mono.just(10),
                StepVerifierOptions.create()
                        .withInitialContext(
                                Context.of("tenant", "alpha")))
        .expectAccessibleContext()
        .assertThat(ctx -> {
            assertTrue(ctx.hasKey("tenant"));
            assertEquals("alpha", ctx.get("tenant"));
        })
        .then()
        .expectNext(10)
        .verifyComplete();
```

`assertTrue` and `assertEquals` come from JUnit Jupiter. Assertions execute when `StepVerifier` runs the scenario, not when building the chain.

### 6.4. Do Not Forget `.then()`

After `expectAccessibleContext()`, methods like `contains`, `hasKey`, `matches`, and `assertThat` belong to `ContextExpectations`. You must call `.then()` to return to the builder for `expectNext`, `expectComplete`, `expectError`, etc.

Structurally wrong:

```java
// Invalid: ContextExpectations has no expectNext.
// .expectAccessibleContext().contains("tenant", "alpha").expectNext("alpha")
```

Right:

```java
.expectAccessibleContext()
.contains("tenant", "alpha")
.then()
.expectNext("alpha")
.verifyComplete();
```

## 7. `expectNoAccessibleContext()` Does Not Mean "Missing Key"

`expectNoAccessibleContext()` is a specialized API asserting that `StepVerifier` **did not observe an accessible Reactor Context propagated** during the subscription phase. This can happen with publishers that do not participate in Reactor context infrastructure or publishers from external libraries.

It is **not** equivalent to asking:

```text
Does the Context exist yet lack the "tenant" key?
```

To test for a missing business key:

- Create a subscriber without supplying that key.
- Use `Mono.deferContextual(...)` to read and emit an error/fallback per contract.
- Use `expectError(...)` or `expectNext(...)` to assert behavior.

Example:

```java
Mono<String> requireTenant = Mono.deferContextual(ctx -> {
    if (!ctx.hasKey("tenant")) {
        return Mono.error(new IllegalStateException("tenant missing"));
    }
    return Mono.just(ctx.get("tenant"));
});

StepVerifier.create(requireTenant)
        .expectErrorMatches(error ->
                error instanceof IllegalStateException
                && "tenant missing".equals(error.getMessage()))
        .verify();
```

This accurately tests the **missing key** condition without relying on whether an external publisher supports Context propagation.

### When Should You Not Call `expectNoAccessibleContext()`?

- To check that a tenant is absent.
- To check that a JWT claim is absent.
- To assert that a Spring Security user is unauthenticated.
- To assert Context size equals 0.
- To test a simple pure Reactor operator when unsure about its accessibility contract.

When the goal is unauthenticated access, test service behavior or `ReactiveSecurityContextHolder.getContext()` directly.

## 8. `contextWrite` Writes from Downstream to Upstream

This rule often yields surprising results.

```java
Mono<String> source = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("tenant", "missing")));

Mono<String> result = source
        .contextWrite(ctx -> ctx.put("tenant", "inner"))
        .contextWrite(ctx -> ctx.put("tenant", "outer"));
```

Expected result:

```text
inner
```

`.contextWrite("outer")` is closer to the subscriber so it runs first in the subscription phase. `.contextWrite("inner")` is closer to the source so it overwrites the key for the upstream source.

**Do not reason purely from top-to-bottom Java source order while ignoring subscription direction.**

### 8.1. `contextWrite` Only Changes Context Visible Upstream

```java
Mono<String> upstream = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("tenant", "missing")))
        .contextWrite(ctx -> ctx.put("tenant", "inner"));

Mono<String> result = upstream.flatMap(value ->
        Mono.deferContextual(ctx ->
                Mono.just(value + "|" +
                        ctx.getOrDefault("tenant", "missing"))));
```

With a subscriber supplying no tenant, the expected value is:

```text
inner|missing
```

Because:

- The source to the left of `.contextWrite` sees `"inner"`.
- Downstream `flatMap` does not inherit a new Context from upstream.
- The inner `Mono.deferContextual(...)` inside `flatMap` sees the actual subscriber's Context, not modifications scoped solely upstream of the prior operator.

This is the kind of bug that normal output-only tests can miss. Write tests verifying both the read site and write site of Context.

### 8.2. Combining Initial Context with Overrides

If `StepVerifier` supplies `"tenant"="outer"` on the subscriber, a source with `.contextWrite(... "inner")` will read `"inner"`, while downstream parts outside that override scope still see `"outer"`.

Note on `expectAccessibleContext()`: that assertion checks **the Context visible to the verifier at the subscription phase**, not a guarantee that every operator in a chain with multiple `contextWrite` calls sees the exact same Context. To verify values at critical read points, have `deferContextual` emit the value and assert the signals.

## 9. Two Subscribers Must Be Independent

An essential test in multi-tenant services:

```java
Mono<String> shared = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("tenant", "public")));

StepVerifier.create(
                shared,
                StepVerifierOptions.create()
                        .withInitialContext(Context.of("tenant", "A")))
        .expectNext("A")
        .verifyComplete();

StepVerifier.create(
                shared,
                StepVerifierOptions.create()
                        .withInitialContext(Context.of("tenant", "B")))
        .expectNext("B")
        .verifyComplete();
```

A single shared Publisher is subscribed to twice with two different Contexts. Results do not bleed across subscriptions.

### 9.1. Verifying When Context Is Read

Use `AtomicInteger` to prove Context reading occurs only at subscription time:

```java
AtomicInteger reads = new AtomicInteger();

Mono<String> source = Mono.deferContextual(ctx -> {
    reads.incrementAndGet();
    return Mono.just(ctx.getOrDefault("tenant", "public"));
});

assertEquals(0, reads.get());

StepVerifier.create(
                source,
                StepVerifierOptions.create()
                        .withInitialContext(Context.of("tenant", "A")))
        .expectNext("A")
        .verifyComplete();

assertEquals(1, reads.get());
```

This tests **deferred execution**, not performance benchmarking.

### 9.2. Do Not Store Tenant in a Static Field

Anti-pattern:

```java
static String currentTenant;
```

If request A sets `"A"` and request B sets `"B"` before A reads the field again, tenants get mixed up. Use Reactor Context or pass validated tenant arguments instead of global mutable state.

## 10. Context and `map`, `flatMap`, `concatMap`

### 10.1. `map` Only Receives Stream Values

```java
Mono<String> item = Mono.just("book")
        .map(value -> value.toUpperCase());
```

The `map` lambda receives `value`, with no `ContextView` parameter. To read Context inside logic that needs it, use a Context-aware operator:

```java
Mono<String> labeled = Mono.just("book")
        .flatMap(value -> Mono.deferContextual(ctx ->
                Mono.just(ctx.getOrDefault("tenant", "public") + ":" + value)));
```

### 10.2. `flatMap` and Inner Publishers

```java
Flux<String> result = Flux.just("one", "two")
        .flatMap(value ->
                Mono.deferContextual(ctx ->
                        Mono.just(ctx.get("tenant") + ":" + value)));
```

In a normal Reactor pipeline, inner publishers can read the corresponding subscription's Context. `flatMap` does not guarantee output order when inner publishers are asynchronous. If ordering is required, use `concatMap`.

### 10.3. `concatMap` When Ordering Matters

```java
Flux<String> result = Flux.just("one", "two")
        .concatMap(value ->
                Mono.deferContextual(ctx ->
                        Mono.just(ctx.get("tenant") + ":" + value)));
```

Expected:

```text
A:one
A:two
```

when the subscriber has `"tenant"="A"`.

Do not use `ThreadLocal` variables or global mutable counters in place of Context propagation when multiple inner publishers run concurrently.

## 11. Context and Schedulers: Do Not Equate with ThreadLocal

A flow can switch schedulers:

```java
Mono<String> result = Mono.just("item")
        .publishOn(Schedulers.parallel())
        .flatMap(value -> Mono.deferContextual(ctx ->
                Mono.just(ctx.getOrDefault("tenant", "public")
                        + ":" + value)));
```

When `StepVerifier` supplies `tenant` in Context, the inner `deferContextual` still reads it within the reactive chain even though execution switched threads.

```java
StepVerifier.create(
                result,
                StepVerifierOptions.create()
                        .withInitialContext(Context.of("tenant", "A")))
        .expectNext("A:item")
        .expectComplete()
        .verify(Duration.ofSeconds(3));
```

However:

```java
ThreadLocal<String> tenant = new ThreadLocal<>();
```

is not automatically propagated across schedulers by Reactor by default. A test running on a single thread can accidentally "pass" when code relies on `ThreadLocal`, and then fail in environments with `publishOn`/`subscribeOn`.

### 11.1. Micrometer Context Propagation

Reactor can integrate `io.micrometer:context-propagation` to bridge values between Reactor Context and `ThreadLocal` under configured conditions. APIs like `contextCapture()`, `Hooks.enableAutomaticContextPropagation()`, and `ThreadLocalAccessor` belong to that propagation mode.

That is a **different** mechanism from standard Reactor Context. Do not assume calling `contextWrite` automatically populates MDC `ThreadLocal` in every callback.

When testing Micrometer propagation:

- Register the appropriate `ThreadLocalAccessor`.
- Control when global hooks are enabled/disabled.
- Avoid configuration leaks between tests running in parallel.
- Verify restoration/cleanup, not just presence inside callbacks.
- Beware that global hooks can affect Publishers created before or after.

In most business services, reading Reactor Context directly with `deferContextual` is simpler and easier to test than bridging with `ThreadLocal`.

## 12. Context in Spring WebFlux HTTP Requests

A WebFlux `WebFilter` can put a trace ID or verified tenant ID into Reactor Context for downstream services to read.

Illustrative example:

```java
@Component
public class TraceContextWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String traceId = UUID.randomUUID().toString();

        return chain.filter(exchange)
                .contextWrite(ctx -> ctx.put("traceId", traceId));
    }
}
```

Main imports:

```java
import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;
```

Downstream service:

```java
public Mono<String> traceId() {
    return Mono.deferContextual(ctx ->
            Mono.just(ctx.getOrDefault("traceId", "missing")));
}
```

This is how to test Context at the service layer without an HTTP server: use `StepVerifierOptions.withInitialContext` to reproduce the context that `WebFilter` would supply.

### 12.1. Trust Boundary

For a tenant ID or user identity, a `WebFilter` must never blindly trust a client-supplied header like `X-Tenant-Id`. Authenticate and authorize before placing an identity into Context. `StepVerifier` only proves data propagation; it does **not** prove the data source is trustworthy.

### 12.2. Testing at Two Layers

- **Service unit tests**: inject Context via `withInitialContext(...)` and verify outputs/errors.
- **`WebTestClient` integration tests**: send HTTP requests through the filter chain and confirm the final request sees the right context, while also testing authentication/authorization if present.

Both are needed when metadata is set in a `WebFilter` and consumed inside a service.

## 13. Spring Security Context in Reactor

Spring Security Reactive stores `SecurityContext` in Reactor Context and reads it via:

```java
ReactiveSecurityContextHolder.getContext()
```

Service example:

```java
public Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .map(securityContext ->
                    securityContext.getAuthentication().getName());
}
```

A unit test can build a suitable `Authentication` and attach it to Context:

```java
Authentication authentication =
        new UsernamePasswordAuthenticationToken(
                "alice",
                "unused",
                List.of(new SimpleGrantedAuthority("ROLE_READER")));

Mono<String> currentUser =
        ReactiveSecurityContextHolder.getContext()
                .map(security ->
                        security.getAuthentication().getName())
                .contextWrite(
                        ReactiveSecurityContextHolder
                                .withAuthentication(authentication));

StepVerifier.create(currentUser)
        .expectNext("alice")
        .verifyComplete();
```

This tests **the service reading an already-present principal from Reactor Context**. It does **not** verify passwords, JWT signatures, issuers, audiences, CSRF, or the HTTP security filter chain.

To test full endpoint authentication/authorization, use `WebTestClient` with Spring Security Test or integration tests with real credentials as appropriate.

### 13.1. Do Not Hardcode Spring Security's Internal Context Key

Spring Security manages how `SecurityContext` is stored in Reactor Context. Never put `"spring.security.context"` or a guessed key into `Context.of(...)` expecting Spring Security to read it.

Use the public API:

```java
ReactiveSecurityContextHolder.withAuthentication(authentication)
```

or Spring Security testing support, avoiding reliance on private keys that may change.

## 14. Context Across `WebClient` and Network Boundaries

Reactor Context is **internal metadata of a single JVM subscription**. When an application makes an outbound HTTP call with `WebClient` or RSocket to another process, Context does not automatically turn into HTTP headers, RSocket metadata, or trace context in the other process.

Example:

```text
Spring WebFlux service A
    |
    | Reactor Context: traceId=trace-1
    |
    v
WebClient outbound HTTP
    |
    | HTTP headers only contain what the client/filter explicitly sends
    v
Service B
```

To propagate a trace ID over the network, you need a filter/interceptor/tracing library that copies permitted metadata into headers and a receiver that validates/reconstructs context. Never forward access tokens blindly to every target host.

### 14.1. Context Tests Do Not Replace Metadata Integration Tests

A `StepVerifier` test:

```java
StepVerifier.create(service.send(...), options.withInitialContext(...))
```

only verifies how publishers in the current process see Context. It does not prove a real `WebClient` sent `traceparent`, `X-Request-Id`, or any header. Add MockWebServer/WireMock or an HTTP test server to verify outbound requests.

### 14.2. Tenant and Security Data

Even when tenant data sits in Reactor Context, outbound APIs need explicit tenant/authorization policies. Reactor Context does not automatically encrypt, authenticate, or sign metadata over the wire.

## 15. Techniques for Testing Missing, Wrong-Type, or Overwritten Keys

Cover at least three cases.

### 15.1. Missing Required Key

```java
Mono<String> required = Mono.deferContextual(ctx -> {
    if (!ctx.hasKey("tenant")) {
        return Mono.error(
                new IllegalStateException("tenant missing"));
    }
    return Mono.just(ctx.get("tenant"));
});

StepVerifier.create(required)
        .expectErrorMatches(error ->
                error instanceof IllegalStateException
                && "tenant missing".equals(error.getMessage()))
        .verify();
```

This is a negative test with a clear terminal error.

### 15.2. Wrong Value Type

Because keys and values are `Object`, the following code can fail at runtime if Context schemas are inconsistent:

```java
Mono<String> readTenant = Mono.deferContextual(ctx -> {
    String tenant = ctx.get("tenant");
    return Mono.just(tenant);
});

StepVerifier.create(
                readTenant,
                StepVerifierOptions.create()
                        .withInitialContext(Context.of("tenant", 123)))
        .expectError(ClassCastException.class)
        .verify();
```

In production, define consistently typed keys or clear wrapper types to avoid key mix-ups. Avoid reusing a generic `"id"` string for differently typed metadata across libraries.

### 15.3. Intentional vs. Unintended Scope Overrides

```java
Mono<String> source = Mono.deferContextual(ctx ->
        Mono.just(ctx.get("tenant")));

Mono<String> result =
        source.contextWrite(ctx -> ctx.put("tenant", "inner"));

StepVerifier.create(
                result,
                StepVerifierOptions.create()
                        .withInitialContext(Context.of("tenant", "outer")))
        .expectNext("inner")
        .verifyComplete();
```

If a service is designed **not** to overwrite the caller's tenant, this test reveals that an override is happening; fix the service code rather than adjusting the assertion to pass.

## 16. `ContextView` with `get`, `getOrDefault`, and `getOrEmpty`

Choosing which Context read API to use defines the error contract.

| API | When key is missing | When to use |
|---|---|---|
| `get(key)` | Throws exception | Invariant is already established |
| `hasKey(key)` | `false` | Need presence check beforehand |
| `getOrDefault(key, fallback)` | Returns fallback | Optional metadata |
| `getOrEmpty(key)` | `Optional.empty()` | Want explicit optional representation |

Example:

```java
Mono<String> optional = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("traceId", "unknown")));
```

If the key is missing, the test expects `"unknown"`. For a tenant used to partition data, fail when missing rather than silently falling back to an unexpected default tenant.

### 16.1. Keys Should Be Unique and Collision-Resistant

You can use an application-owned object key:

```java
public static final Object TENANT_KEY = new Object();
```

Components within the same module must share the exact same key reference. This prevents collisions with another library's `"tenant"` key. For learning examples and clear public contracts, `String` keys remain easy to read.

### 16.2. Never Store `null` in Context

`Context` is not designed to store `null` values. Use an `Optional`/record or delete the key when absent.

Do not write:

```java
// Invalid per contract:
Context.of("tenant", null);
```

Test "no tenant" by **omitting the key**, not by storing a `null` value.

## 17. Combining Context and Virtual Time

Reactor Context is not tied to a clock. However, if a pipeline includes delays, retries, or timeouts, you can combine `withInitialContext` with `StepVerifier.withVirtualTime(...)`.

```java
StepVerifierOptions options = StepVerifierOptions.create()
        .withInitialContext(Context.of("tenant", "alpha"));

StepVerifier.withVirtualTime(
                () -> Mono.delay(Duration.ofHours(1))
                        .flatMap(tick -> Mono.deferContextual(ctx ->
                                Mono.just(ctx.get("tenant")))),
                options)
        .thenAwait(Duration.ofHours(1))
        .expectNext("alpha")
        .verifyComplete();
```

`withVirtualTime` does not wait a real hour. It uses the virtual scheduler to advance time.

Important conditions:

- Create time-based operators **inside the lambda** passed to `withVirtualTime`.
- Do not create a custom scheduler outside the lambda and expect virtual time to control it.
- Be mindful of timeouts and request demand in tests.
- Avoid mutating global hooks/schedulers when tests run in parallel.

Virtual time verifies timing semantics, whereas `withInitialContext` tests subscriber context. The two mechanisms compose cleanly yet remain orthogonal.

## 18. Runnable Java 17+ Project with Reactor Test

The project demonstrates using Spring Boot 3.3.5 for dependency management, while pure Reactor tests do not need to start a Spring `ApplicationContext`. This keeps tests fast and focused directly on **Reactor Context**.

Includes:

- A service reading tenant/trace ID via `deferContextual`.
- Required tenant and fallback tenant.
- `contextWrite` override scope.
- Inner `flatMap` with Context.
- Isolated Context across subscriptions.
- Async boundary with `publishOn`.
- Assertions: `expectAccessibleContext`, `contains`, `hasKey`, `matches`, `assertThat`, `hasSize`.
- Virtual time + initial Context.
- Spring Security reactive context via the public API.

### 18.1. Directory Structure

```text
reactor-context-testing/
├── pom.xml
└── src/
    ├── main/java/edu/demo/context/
    │   └── ContextGreetingService.java
    └── test/java/edu/demo/context/
        ├── ContextGreetingServiceTests.java
        └── SecurityContextTests.java
```

### 18.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>reactor-context-testing</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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

`spring-boot-starter-security` provides Spring Security core and the reactive context holder. It creates no HTTP endpoints in this project. `reactor-test` is needed only in test scope.

### 18.3. `ContextGreetingService.java`

```java
package edu.demo.context;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class ContextGreetingService {

    public static final String TENANT = "tenant";
    public static final String TRACE_ID = "traceId";

    public Mono<String> greet(String name) {
        return Mono.deferContextual(ctx -> {
            String tenant = ctx.getOrDefault(TENANT, "public");
            String trace = ctx.getOrDefault(TRACE_ID, "none");

            return Mono.just(tenant + ":" + name + ":" + trace);
        });
    }

    public Mono<String> requiredTenant() {
        return Mono.deferContextual(ctx -> {
            if (!ctx.hasKey(TENANT)) {
                return Mono.error(
                        new IllegalStateException("tenant missing"));
            }

            String tenant = ctx.get(TENANT);

            if (tenant.isBlank()) {
                return Mono.error(
                        new IllegalArgumentException("tenant empty"));
            }

            return Mono.just(tenant);
        });
    }

    public Flux<String> markAll(Flux<String> items) {
        return items.concatMap(item ->
                Mono.deferContextual(ctx -> {
                    String tenant =
                            ctx.getOrDefault(TENANT, "public");
                    return Mono.just(tenant + ":" + item);
                }));
    }

    public Mono<String> scopedRead() {
        Mono<String> upstream = Mono.deferContextual(ctx ->
                Mono.just(ctx.getOrDefault(TENANT, "missing")))
                .contextWrite(ctx -> ctx.put(TENANT, "inner"));

        return upstream.flatMap(value ->
                Mono.deferContextual(ctx ->
                        Mono.just(value + "|"
                                + ctx.getOrDefault(TENANT, "missing"))));
    }

    public Mono<String> asyncGreeting(String name) {
        return Mono.just(name)
                .publishOn(Schedulers.parallel())
                .flatMap(value ->
                        Mono.deferContextual(ctx -> {
                            String tenant =
                                    ctx.getOrDefault(TENANT, "public");

                            return Mono.just(tenant + ":" + value);
                        }));
    }
}
```

Explanation:

- `greet` reads tenant and trace ID on subscribe.
- `requiredTenant` emits an error if tenant is absent.
- `markAll` uses `concatMap` to preserve order.
- `scopedRead` shows `contextWrite` applies only upstream.
- `asyncGreeting` verifies Context propagation after `publishOn`.

No method stores tenant in a mutable field, so a singleton service can serve many different subscribers safely.

### 18.4. `ContextGreetingServiceTests.java`

```java
package edu.demo.context;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.util.context.Context;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ContextGreetingServiceTests {

    private final ContextGreetingService service =
            new ContextGreetingService();

    @Test
    void initialContextIsVisibleToPublisherAndVerifier() {
        StepVerifierOptions options = StepVerifierOptions.create()
                .scenarioName("tenant and trace")
                .withInitialContext(Context.of(
                        ContextGreetingService.TENANT, "alpha",
                        ContextGreetingService.TRACE_ID, "req-7"));

        StepVerifier.create(service.greet("An"), options)
                .expectAccessibleContext()
                .contains(ContextGreetingService.TENANT, "alpha")
                .hasKey(ContextGreetingService.TRACE_ID)
                .matches(ctx ->
                                Objects.equals(
                                        ctx.get("traceId"),
                                        "req-7"),
                        "traceId equals req-7")
                .then()
                .expectNext("alpha:An:req-7")
                .verifyComplete();
    }

    @Test
    void contextExpectationsCanAssertExactSmallContext() {
        StepVerifierOptions options = StepVerifierOptions.create()
                .withInitialContext(Context.of(
                        "tenant", "alpha",
                        "traceId", "req-8"));

        StepVerifier.create(Mono.just(10), options)
                .expectAccessibleContext()
                .hasSize(2)
                .containsAllOf(
                        Context.of("tenant", "alpha", "traceId", "req-8"))
                .assertThat(ctx -> {
                    assertTrue(ctx.hasKey("tenant"));
                    assertEquals("alpha", ctx.get("tenant"));
                })
                .then()
                .expectNext(10)
                .verifyComplete();
    }

    @Test
    void missingOptionalContextUsesFallbacks() {
        StepVerifier.create(service.greet("An"))
                .expectNext("public:An:none")
                .verifyComplete();
    }

    @Test
    void missingRequiredTenantIsError() {
        StepVerifier.create(service.requiredTenant())
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                                && "tenant missing".equals(
                                        error.getMessage()))
                .verify();
    }

    @Test
    void blankRequiredTenantIsError() {
        StepVerifier.create(
                        service.requiredTenant(),
                        StepVerifierOptions.create()
                                .withInitialContext(
                                        Context.of("tenant", "")))
                .expectError(IllegalArgumentException.class)
                .verify();
    }

    @Test
    void eachSubscriptionHasItsOwnContext() {
        Mono<String> shared = service.greet("An");

        StepVerifier.create(
                        shared,
                        StepVerifierOptions.create()
                                .withInitialContext(
                                        Context.of("tenant", "A")))
                .expectNext("A:An:none")
                .verifyComplete();

        StepVerifier.create(
                        shared,
                        StepVerifierOptions.create()
                                .withInitialContext(
                                        Context.of("tenant", "B")))
                .expectNext("B:An:none")
                .verifyComplete();
    }

    @Test
    void contextIsReadAtSubscriptionTime() {
        AtomicInteger reads = new AtomicInteger();

        Mono<String> source = Mono.deferContextual(ctx -> {
            reads.incrementAndGet();

            return Mono.just(
                    ctx.getOrDefault("tenant", "public"));
        });

        assertEquals(0, reads.get());

        StepVerifier.create(
                        source,
                        StepVerifierOptions.create()
                                .withInitialContext(
                                        Context.of("tenant", "A")))
                .expectNext("A")
                .verifyComplete();

        assertEquals(1, reads.get());
    }

    @Test
    void contextWriteCanOverrideInitialContext() {
        Mono<String> result = service.requiredTenant()
                .contextWrite(ctx -> ctx.put("tenant", "inner"));

        StepVerifier.create(
                        result,
                        StepVerifierOptions.create()
                                .withInitialContext(
                                        Context.of("tenant", "outer")))
                .expectNext("inner")
                .verifyComplete();
    }

    @Test
    void contextWriteClosestToSourceWinsForThatSource() {
        Mono<String> result = service.requiredTenant()
                .contextWrite(ctx -> ctx.put("tenant", "source"))
                .contextWrite(ctx -> ctx.put("tenant", "subscriber"));

        StepVerifier.create(result)
                .expectNext("source")
                .verifyComplete();
    }

    @Test
    void contextWriteDoesNotModifyDownstreamContext() {
        StepVerifier.create(service.scopedRead())
                .expectNext("inner|missing")
                .verifyComplete();
    }

    @Test
    void downstreamCanStillReadInitialContext() {
        StepVerifier.create(
                        service.scopedRead(),
                        StepVerifierOptions.create()
                                .withInitialContext(
                                        Context.of("tenant", "outer")))
                .expectNext("inner|outer")
                .verifyComplete();
    }

    @Test
    void concatMapRetainsContextAndItemOrder() {
        StepVerifier.create(
                        service.markAll(
                                Flux.just("one", "two", "three")),
                        StepVerifierOptions.create()
                                .withInitialContext(
                                        Context.of("tenant", "A")))
                .expectNext("A:one", "A:two", "A:three")
                .verifyComplete();
    }

    @Test
    void contextSurvivesPublishOnSchedulerSwitch() {
        StepVerifier.create(
                        service.asyncGreeting("An"),
                        StepVerifierOptions.create()
                                .withInitialContext(
                                        Context.of("tenant", "A")))
                .expectNext("A:An")
                .expectComplete()
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void immutableContextOperationsDoNotChangeOriginal() {
        Context original = Context.of("tenant", "A");
        Context updated = original.put("traceId", "t-1");

        assertFalse(original.hasKey("traceId"));
        assertTrue(updated.hasKey("traceId"));
        assertEquals("A", original.get("tenant"));
        assertEquals("A", updated.get("tenant"));
    }

    @Test
    void virtualTimeAndInitialContextWorkTogether() {
        StepVerifierOptions options = StepVerifierOptions.create()
                .withInitialContext(Context.of("tenant", "alpha"));

        StepVerifier.withVirtualTime(
                        () -> Mono.delay(Duration.ofHours(1))
                                .flatMap(tick ->
                                        service.requiredTenant()),
                        options)
                .thenAwait(Duration.ofHours(1))
                .expectNext("alpha")
                .verifyComplete();
    }
}
```

This test suite contains 15 methods covering initial Context setup, `ContextExpectations` checks, fallbacks, negative cases, multiple subscriptions, override scopes, `concatMap`, scheduler switches, immutable context, and virtual time.

The `expectAccessibleContext()` tests use the verifier's own **initial context** as an explicit data source. The `contextWrite` tests read via `deferContextual` to verify override scoping. Separating these two groups avoids confusing "Context visible at one point" with "Context visible to every operator".

### 18.5. `SecurityContextTests.java`

```java
package edu.demo.context;

import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.security.authentication
        .UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority
        .SimpleGrantedAuthority;
import org.springframework.security.core.context
        .ReactiveSecurityContextHolder;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class SecurityContextTests {

    @Test
    void reactiveSecurityContextHolderReadsAuthentication() {
        Authentication authentication =
                new UsernamePasswordAuthenticationToken(
                        "alice",
                        "unused",
                        List.of(new SimpleGrantedAuthority(
                                "ROLE_READER")));

        Mono<String> currentUsername =
                ReactiveSecurityContextHolder.getContext()
                        .map(security ->
                                security.getAuthentication().getName())
                        .contextWrite(
                                ReactiveSecurityContextHolder
                                        .withAuthentication(authentication));

        StepVerifier.create(currentUsername)
                .expectNext("alice")
                .verifyComplete();
    }

    @Test
    void absentSecurityContextDoesNotInventPrincipal() {
        Mono<String> name =
                ReactiveSecurityContextHolder.getContext()
                        .map(security ->
                                security.getAuthentication().getName());

        StepVerifier.create(name)
                .verifyComplete();
    }
}
```

These two tests verify reading `SecurityContext` via the public API. The default outcome when no `SecurityContext` is present is an empty publisher, not a test-invented `"anonymous"` user.

These tests do not validate passwords, tokens, or the HTTP security chain. To test HTTP 401/403 responses, use `WebTestClient` with an appropriate Spring Security configuration.

### 18.6. Running the Tests

In the directory containing `pom.xml`:

```bash
mvn test
```

Expected output when Maven runs successfully:

```text
Tests run: 17, Failures: 0, Errors: 0, Skipped: 0
```

Total declared tests: **15** in `ContextGreetingServiceTests` and **2** in `SecurityContextTests`.

The line above is an **expected outcome**, not an executed run from this authoring environment. In practice, run Maven and verify the Reactor version managed by the Spring Boot BOM.

## 19. Common Mistakes When Testing Reactor Context

| Mistake | Consequence | Fix |
|---|---|---|
| Checking only `expectNext` | Can miss Context propagation | Use `withInitialContext` + `expectAccessibleContext` or assert `deferContextual` output |
| Forgetting `.then()` after `ContextExpectations` | Cannot transition to `expectNext` | Call `.then()` |
| Using `expectNoAccessibleContext()` to check missing tenant | Tests the wrong property | Use `deferContextual` to check missing key |
| Placing `contextWrite` above the reader following data-flow intuition | Operator never sees the key | Follow subscription direction from downstream to upstream |
| Assuming `contextWrite` updates Context for every operator | Downstream reads a different value | Check scope at the actual read site |
| Assuming Context belongs to the `Mono` variable | Two subscribers may need different contexts | Test each subscriber with its own initial context |
| Using `ThreadLocal` as the primary tenant holder | Context lost on scheduler switches | Use Reactor Context |
| Calling `Context.get` on a missing key | `NoSuchElementException` or similar error | Use `hasKey`/`getOrDefault`/`getOrEmpty` per contract |
| Using the same key with two object types | `ClassCastException` | Define typed keys and a consistent schema |
| Storing mutable objects in Context | Races under concurrent edits | Use immutable values or explicit synchronization |
| Storing Context in a static field | Data leaks across requests | Read only within the subscription |
| Asserting exact `hasSize` when tracing/security adds keys | Brittle tests fail when instrumentation changes | Assert the keys/values you own |
| Calling `StepVerifier.create` without `verify...` | Scenario never runs | End with `verifyComplete`, `verifyError`, or `verify` |
| Unbounded real-async tests | Tests can hang | Use `verify(Duration)` or virtual time appropriately |
| Creating `Mono.delay` outside the virtual time supplier | Virtual scheduler has no control | Create the publisher inside the `withVirtualTime` lambda |
| Enabling global propagation `Hooks` in tests without cleanup | Affects other tests | Set up/restore hooks carefully |
| Assuming Context crosses HTTP/WebSocket/RSocket automatically | Metadata never reaches the other service | Propagate explicitly at network boundaries |
| Trusting an unverified header as an authenticated `Authentication` | Privilege escalation | Use an authentication manager / Spring Security |
| Putting raw tokens/PII in logs or test snapshots | Information leak | Redact/mask and assert safe metadata only |
| Calling `block()` in a WebFlux service | Blocks the event loop | Return/compose reactive publishers |
| Sharing a `"tenant"` key owned by two libraries | Collisions and unexpected overrides | Use distinct keys or wrapper types |

## 20. Checklist for Writing Good Tests

### Context Design

- Which keys are required, and which are optional?
- Are key values consistently typed?
- Which component creates each key, and who may overwrite it?
- Is data immutable and free of raw secrets?
- Is Context populated at a trusted boundary?

### Unit Tests with StepVerifier

- Is `withInitialContext` used for subscriber-supplied metadata?
- Is `.expectAccessibleContext().contains(...)` used for propagation where needed?
- Is `.then()` placed before sequence assertions?
- Are `onNext`, completion, or errors asserted per contract?
- Are missing keys and fallbacks tested?
- Are `contextWrite` overrides tested?
- Are multiple independent subscribers tested?
- Are nested `flatMap`/`concatMap` flows tested if used?
- Are `publishOn`/`subscribeOn` execution switches tested?
- Are timeouts set on async tests that might fail to complete?

### Spring WebFlux Integration

- Does `WebFilter` populate Context only after verifying metadata?
- Do controllers/services read via `deferContextual`?
- Is security context managed by Spring Security?
- Are there separate HTTP 401/403 tests with `WebTestClient`?
- Does outbound `WebClient` propagate headers per contract?
- Is there a concurrent two-request test to catch tenant bleed?

### Operations

- Are trace IDs / correlation IDs attached consistently?
- Do logs avoid dumping full Reactor Contexts containing credentials?
- Is MDC/`ThreadLocal` propagation configured and tested separately?
- Are there zero static contexts holding user state?
- Are zero global hooks left enabled after tests?
- Does tracing instrumentation avoid breaking rigid Context-size tests?

## 21. Self-Check Exercises

**Exercise 1.** Does `Context` belong to the Publisher or the subscriber?

**Answer:** It belongs to the subscription/subscriber; the same Publisher can be subscribed to multiple times with different Contexts.

**Exercise 2.** Does `context.put(...)` mutate the original `Context` object?

**Answer:** No. `Context` is immutable; `put` returns a new `Context`.

**Exercise 3.** Which API supplies a tenant to `StepVerifier`'s subscriber?

**Answer:** `StepVerifierOptions.create().withInitialContext(Context.of("tenant","alpha"))`.

**Exercise 4.** When is `expectAccessibleContext()` used?

**Answer:** When asserting that Context propagated and is observable during the subscription phase; chain `.contains`, `.hasKey`, `.matches`, `.assertThat`.

**Exercise 5.** After `.expectAccessibleContext().contains(...)`, what must be called before `expectNext`?

**Answer:** `.then()`.

**Exercise 6.** Does `expectNoAccessibleContext()` prove the `"tenant"` key is missing?

**Answer:** No. It checks Reactor Context accessibility during the subscription phase. Missing business keys should be tested via `deferContextual` and output/error contracts.

**Exercise 7.** Why can a `contextWrite` closer to the source overwrite a downstream value?

**Answer:** Because Context flows from the subscriber upstream at subscribe time. Operators closer to the source apply their transformation later, so the source sees the newer value.

**Exercise 8.** Does `publishOn` lose Reactor Context?

**Answer:** In normal Reactor chains, Context stays with the subscription; `ThreadLocal` has no such guarantee unless a propagation bridge is configured.

**Exercise 9.** Is a unit test reading `ReactiveSecurityContextHolder` enough to prove a JWT is valid?

**Answer:** No. It only tests that the service reads `SecurityContext`; JWT signature/issuer/audience/expiry require testing the authentication pipeline.

**Exercise 10.** When you need to advance one virtual hour in a Context test, which API do you use?

**Answer:** `StepVerifier.withVirtualTime(...)` and `thenAwait(Duration.ofHours(1))`; create the time-based publisher inside the supplier lambda while passing `withInitialContext` in `StepVerifierOptions`.

## 22. Key Takeaways

- Reactor `Context` is an immutable key–value store for subscription-scoped metadata, not `ThreadLocal` or `ApplicationContext`.
- `ContextView` provides read-only APIs; `Context` adds `put`, `delete`, `putAll`.
- `contextWrite` passes metadata from downstream to upstream at subscribe time.
- `deferContextual` reads Context at the exact position and moment the publisher is subscribed to.
- `StepVerifierOptions.withInitialContext(Context)` sets the initial Context on the test subscriber.
- `expectAccessibleContext()` supports `contains`, `hasKey`, `hasSize`, `matches`, `assertThat`, `containsAllOf`; remember `.then()` before sequence assertions.
- `expectNoAccessibleContext()` is **not** the way to test for a single missing key.
- Verify both Context propagation and `onNext`/`onError`/`onComplete`.
- Multiple subscriptions to the same Publisher can carry different Contexts.
- `contextWrite` applies only to its upstream scope; verify the value at the actual operator reading it.
- Reactor Context propagates across standard Reactor operators/schedulers; `ThreadLocal` and MDC require separate bridging mechanisms.
- `ReactiveSecurityContextHolder` uses Reactor Context, yet context unit tests do not replace authentication integration tests.
- Context does not cross network boundaries automatically; HTTP/RSocket metadata requires explicit propagation.
- Keep Context small, free of mutable shared state or sensitive credentials/log payloads.
- Testing with initial Context, missing keys, overrides, multiple subscribers, async boundaries, and virtual time catches most propagation bugs.

**Quick diagnostic question:** *Who creates the key, which subscription uses it, which operator reads it, where does `contextWrite` sit relative to the source, and did the test verify both Context and outcome?*

## 23. Official References

- Reactor Core Reference — **Adding a Context to a Reactive Sequence**: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Reactor Core Reference — **Testing a Sequence with StepVerifier**: https://projectreactor.io/docs/core/release/reference/testing.html
- Reactor Test Javadoc — **StepVerifier**: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
- Reactor Test Javadoc — **StepVerifier.ContextExpectations**: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.ContextExpectations.html
- Reactor Test Javadoc — **StepVerifierOptions**: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifierOptions.html
- Reactor Core Javadoc — **Context / ContextView**: https://projectreactor.io/docs/core/release/api/reactor/util/context/Context.html
- Spring Security Reference — **Reactive Method Security and Reactor Context**: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security API — **ReactiveSecurityContextHolder**: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Framework Reference — **WebFlux WebFilter**: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Micrometer — **Context Propagation**: https://docs.micrometer.io/context-propagation/reference/