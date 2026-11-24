# Diagnosing Context Loss from Manual `subscribe()` or Out-of-Chain Publishers in Spring Security WebFlux

## 1. Learning Objectives and Failure Scenario

This lesson belongs to **Spring Security - reactive**, under **Migration and debugging**. Its focus is determining **why `ReactiveSecurityContextHolder.getContext()` returns `Mono.empty()` or cannot see the current user** even though the request passed authentication—especially when code calls `.subscribe()` manually, `.block()`, spawns background threads, or uses a `Publisher` executed outside the HTTP request's reactive chain.

After this lesson, the reader should be able to:

1. Distinguish **per-`Subscriber` Reactor `Context`** from `ThreadLocal`, Servlet `SecurityContextHolder`, and typical request-scoped variables.
2. Locate the subscription break by tracing the pipeline from HTTP handler/filter down to services and async clients.
3. Distinguish a **Publisher constructed elsewhere yet still composed** (usually Context-safe) from a **Publisher subscribed separately** (does not automatically receive the request's Reactor Context).
4. Fix issues using properly scoped `flatMap`, `then`, `zipWhen`, `Mono.when`, `defer`/`deferContextual`, and `contextWrite` operators.
5. Test both the failing case and the fixed case with `StepVerifier`, then verify through `WebTestClient` in a real application.
6. Avoid accidentally leaking identities across requests, "fixing" bugs by granting fake privileges, or running security-sensitive tasks outside reactive chain control.

### Common Symptoms

- A protected endpoint received a valid login/JWT; the controller sees `Authentication`, yet a service called via `subscribe()` inside `doOnNext` sees only anonymous or an empty `getContext()`.
- `@PreAuthorize` on a reactive service yields unexpected results when important work is triggered outside the `Publisher` returned by the method.
- Async auditing/events observe a `null` user while the request returns 200; sometimes the bug only surfaces when callbacks run on another scheduler/executor.
- Code stores a `Mono` in a bean field and reuses it; some places see the right user, others see an earlier user, or the `Mono` never executes because nothing subscribed to it.
- `doOnError` on the request misses exceptions from a "fire-and-forget" task, sending errors to a separate error handler.

These symptoms do not by themselves prove Spring Security is broken. The first step is classifying the root cause: unauthenticated request, detached subscriber, misplaced operator, wrongly cached data, or incompatible callback/ThreadLocal integration.

## 2. The Right Model: `SecurityContext` Lives in the Subscription's Reactor `Context`

In WebFlux, **`ReactiveSecurityContextHolder`** is the reactive API for reading `SecurityContext`. Spring Security injects the proper context into the request stream (for example via `ReactorContextWebFilter` and security filters). It is part of **Reactor Context**, accessed per `Subscriber`—not a default `ThreadLocal` always present on every thread.

```text
HTTP request
  └─ SecurityWebFilterChain authenticates
       └─ Request Subscriber carries Reactor Context
            └─ handler Mono/Flux
                 ├─ flatMap(service.read())     -> same subscriber context
                 ├─ then(audit.write())         -> same subscriber context
                 └─ zipWhen(profile.load())     -> still composed into request
```

Reactor separates **assembly** (building the pipeline description) from **subscription** (execution). Context attaches to the subscriber at subscription time and flows from downstream upward along the operator chain. `contextWrite(...)` creates a new Context for **operators upstream of itself**. `Mono.deferContextual(...)` reads Context at subscription time. Consequently:

- The same `Mono` can be subscribed twice with two different Contexts.
- Constructing a `Mono` outside a method does not automatically drop context. **The subscription path and `contextWrite` scope decide.**
- `publishOn`/`subscribeOn` switch schedulers or threads, and **do not by default drop Reactor Context** within a valid Reactor pipeline.
- Traditional `SecurityContextHolder.getContext()` uses ThreadLocal and is not the general API for reading reactive identity. Use `ReactiveSecurityContextHolder.getContext()` or pass `Authentication`/principal explicitly as parameters by design.
- Reactor Context normally flows across `flatMap`, `concatMap`, `then`, `zip`, and many other composition operators via operator-managed inner subscriptions. Never equate those with a manual `.subscribe()` call in business code.

Basic API:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
```

This is an **illustrative snippet**; a complete test project appears in Section 5. When no `SecurityContext` exists on the subscriber, `getContext()` can complete empty. Never replace permission checks with `.defaultIfEmpty("admin")` or a fabricated identity. In tests, a sentinel string like `"ANONYMOUS"` to observe the empty case is fine, yet **never grant privileges** to that user in production.

## 3. Root Error: Manual `.subscribe()` Opens a New Subscription

The example below illustrates the **wrong way** to run auditing in application code (snippet only, not a standalone project):

```java
public Mono<String> handleRequest(String itemId) {
    auditService.recordCurrentUser("view-item:" + itemId)
        .subscribe(); // WRONG: creates a separate subscriber detached from the HTTP request

    return itemService.loadDescription(itemId);
}
```

`recordCurrentUser(...)` may call `ReactiveSecurityContextHolder.getContext()`. Calling `.subscribe()` directly creates a second subscriber that by default does not carry the request Context subscribed by the server. Auditing may also run **before** access decisions finish, execute with unbounded concurrency, outlive a cancelled request, and emit errors unseen by the returned `Mono`.

Replace with **composition**:

```java
public Mono<String> handleRequest(String itemId) {
    return itemService.loadDescription(itemId)
        .flatMap(description ->
            auditService.recordCurrentUser("view-item:" + itemId)
                .thenReturn(description));
}
```

In the fixed version, `recordCurrentUser` returns `Mono<Void>` and lives inside the pipeline subscribed by the server. `thenReturn(description)` emits the description **only after auditing finishes**. If auditing fails, the request fails unless an explicit handling policy applies; if the request is cancelled, cancellation can propagate to that task. This also guarantees responses do not report completion before business-required steps finish.

Choose operators according to the operation's semantics:

| Need | Typically appropriate operator | Notes |
| --- | --- | --- |
| Call async to produce the next value | `flatMap(value -> service.load(value))` | Never call `subscribe()` inside the lambda |
| Run async then retain original value | `flatMap(value -> audit.write(value).thenReturn(value))` | Makes audit a mandatory step |
| Run A then B, discarding A's value | `a.then(b)` or `a.then(Mono.defer(() -> b))` | Both join the same pipeline |
| Wait for multiple Publishers to finish | `Mono.when(a, b)` | If one fails, the aggregate reflects errors/cancellation per operator rules |
| Enrich with a related value | `zipWhen(value -> service.find(value))` | Operator manages inner Context |
| Synchronous logging without async Publisher | `doOnNext`, `doOnError`, `doFinally` | Never hide an async `.subscribe()` inside a callback |
| Build Publisher only at subscription time | `Mono.defer(() -> createPublisher())` | Defers creation, yet still must be composed |
| Read Reactor Context at subscription time | `Mono.deferContextual(ctx -> ...)` | Ideal for custom context entries |

`doOnNext(v -> service.write(v))` **never executes** the returned `Mono` unless something subscribes to it; `doOnNext(v -> service.write(v).subscribe())` creates a detached subscription instead. Neither is equivalent to `flatMap(v -> service.write(v))`.

### What Happens with `block()`?

```java
String username = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .block(); // Do not use on WebFlux processing threads.
```

`block()` creates its own subscription and blocks the thread, with no guarantee of carrying the request's Reactor Context into that new subscription. On event-loop threads, it can also throw blocking-related exceptions or stall throughput. The right approach is returning `Mono<String>` and continuing with `flatMap`/`map`, or using framework-injected principals.

## 4. Publishers "Outside the Chain": Distinguishing Two Cases

### 4.1. Publisher Built Ahead of Time Yet **Composed When Used**: Usually Still Works

```java
private final Mono<String> userSource =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());

// Inside a request-handling method:
public Mono<String> decorate(String itemId) {
    return itemService.loadDescription(itemId)
        .flatMap(value -> userSource.map(user -> user + ": " + value));
}
```

`userSource` was assembled ahead of time, yet `flatMap` subscribes to it **inside the request pipeline**. `ReactiveSecurityContextHolder.getContext()` reads Context at subscription time and therefore sees the right user. When using this pattern, still watch for reusability, side effects, and sensitive data; never apply `cache()` to a user-dependent Publisher.

### 4.2. Publisher Subscribed Elsewhere: Request Context Does Not Follow Automatically

```java
private final Mono<String> userSource =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());

// Inside a controller/service:
public Mono<String> bad(String itemId) {
    userSource.subscribe(user -> auditSink.send(user, itemId));
    return Mono.just("accepted");
}
```

A second subscriber is created directly, so the Context it observes does not inherit the request's Context. When `getContext()` completes empty, the success callback may **never even execute**. Returning `"accepted"` also gives no guarantee the event was recorded.

### 4.3. Unsubscribed Publisher: Operation Never Runs

```java
public Mono<String> bad(String id) {
    itemService.save(id);     // only creates a Mono, never runs
    return Mono.just("saved"); // falsely reports success
}
```

Fix:

```java
public Mono<String> good(String id) {
    return itemService.save(id).thenReturn("saved");
}
```

### 4.4. Beware `cache()`, `share()`, and Hot Publishers

```java
// Dangerous if shared across different requests:
private final Mono<String> cachedUser = currentUsername().cache();
```

If the first subscription under Alice's account caches `"alice"`, a subsequent request from Bob can receive `"alice"` from cache without reading the fresh context. This is **cross-request data/privilege leakage**, not merely an empty-context bug. Never cache identity-dependent results on a shared singleton `Mono`; if caching data is truly required, key by tenant/user and enforce authorization, TTL, and invalidation explicitly. `Sinks.Many`/hot streams have independent subscribers; never assume a producer's Context automatically propagates to every consumer.

Whether a `Publisher` is **cold** or **hot**, whether it has been subscribed to, and who holds references determine how it behaves; variable placement in a Java file alone is insufficient to conclude context loss.

## 5. Runnable JUnit 5 + StepVerifier Project to Reproduce and Fix the Bug

The following example uses **Java 17, Spring Boot 3.5.0, Reactor Test, and Spring Security 6.x**. This project runs Reactor tests **without needing Redis, an IdP, or an HTTP server**. It directly demonstrates the difference between detached subscriptions, composed operators, `contextWrite` boundaries, and shared caches. This is a test suite for **Context mechanics**; real HTTP testing is covered in Section 8.

Create the layout:

```text
reactive-context-diagnostics/
├── pom.xml
└── src/test/java/example/context/ContextLossTest.java
```

**`pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>reactive-context-diagnostics</artifactId>
    <version>1.0.0</version>
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
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Spring Boot dependency management selects compatible Reactor and Spring Security versions. `spring-boot-starter-test` includes JUnit Jupiter, Reactor Test, and assertion utilities; no `@SpringBootApplication` class is needed just to run the context-free unit tests below.

**`src/test/java/example/context/ContextLossTest.java`:**

```java
package example.context;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ContextLossTest {
    private static final Authentication ALICE =
        new TestingAuthenticationToken("alice", "test", "ROLE_USER");
    private static final Authentication BOB =
        new TestingAuthenticationToken("bob", "test", "ROLE_USER");

    // "ANONYMOUS" is solely a test observation value,
    // NEVER an authorized production identity.
    private static Mono<String> currentUsername() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .defaultIfEmpty("ANONYMOUS");
    }

    @Test
    void directContextWriteIsVisibleAtSubscription() {
        Mono<String> request = currentUsername()
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(ALICE));

        StepVerifier.create(request)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void manualSubscribeInsidePipelineCreatesDetachedSubscriber() {
        AtomicReference<String> observed = new AtomicReference<>("not-run");

        Mono<String> request = Mono.defer(() -> {
            // Intentionally models the anti-pattern for diagnosis.
            // currentUsername() is a synchronous Mono in this example.
            currentUsername().subscribe(observed::set);
            return Mono.just("response-complete");
        }).contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(ALICE));

        StepVerifier.create(request)
            .expectNext("response-complete")
            .verifyComplete();

        assertEquals("ANONYMOUS", observed.get());
    }

    @Test
    void flatMapKeepsInnerPublisherUnderRequestContext() {
        Mono<String> request = Mono.just("request")
            .flatMap(ignored -> currentUsername())
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(ALICE));

        StepVerifier.create(request)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void publisherBuiltOutsideChainStillUsesSubscriptionContext() {
        Mono<String> builtEarlier = currentUsername();

        Mono<String> request = Mono.just("request")
            .flatMap(ignored -> builtEarlier)
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(ALICE));

        StepVerifier.create(request)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void publishOnChangesThreadButKeepsReactorContext() {
        Mono<String> request = Mono.just("request")
            .publishOn(Schedulers.parallel())
            .flatMap(ignored -> currentUsername())
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(ALICE));

        StepVerifier.create(request)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void contextWriteOnlyAffectsItsUpstreamScope() {
        Mono<String> wrongScope = Mono.just("ready")
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(ALICE))
            .then(currentUsername());

        StepVerifier.create(wrongScope)
            .expectNext("ANONYMOUS")
            .verifyComplete();

        Mono<String> correctScope = Mono.just("ready")
            .then(currentUsername())
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(ALICE));

        StepVerifier.create(correctScope)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void eachSubscriptionCanSeeDifferentUser() {
        Mono<String> reusable = currentUsername();

        StepVerifier.create(reusable.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(ALICE)))
            .expectNext("alice")
            .verifyComplete();

        StepVerifier.create(reusable.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(BOB)))
            .expectNext("bob")
            .verifyComplete();
    }

    @Test
    void sharedCacheDemonstratesCrossUserLeakageAntiPattern() {
        // Intentionally demonstrates what must never be written in production.
        Mono<String> cachedAcrossRequests = currentUsername().cache();

        StepVerifier.create(cachedAcrossRequests.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(ALICE)))
            .expectNext("alice")
            .verifyComplete();

        // Emits "alice" even though the new subscriber's context is Bob.
        StepVerifier.create(cachedAcrossRequests.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(BOB)))
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void composedAsyncFailureReachesRequest() {
        Mono<String> request = currentUsername()
            .flatMap(user -> Mono.<Void>error(
                    new IllegalStateException("audit unavailable"))
                .thenReturn(user))
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(ALICE));

        StepVerifier.create(request)
            .expectErrorMatches(error ->
                error instanceof IllegalStateException
                    && "audit unavailable".equals(error.getMessage()))
            .verify();
    }
}
```

**Run:**

```bash
mvn test
```

When Maven can resolve dependencies and JDK 17+ is installed, **9 tests are expected to pass**; exact stdout depends on Maven/Surefire. The two tests `manualSubscribe...` and `sharedCache...` are written to **pin down the failure modes**: they pass because `"ANONYMOUS"` and `"alice"` represent the exact wrong-context outcomes of the modeled anti-patterns. Those are learning regression tests, **not desired production system behavior**.

Key takeaways from the tests:

- `flatMap` runs inner publishers within the current subscription's pipeline.
- A `Mono` assembled outside yet subscribed via `flatMap` still reads the right context.
- `publishOn` switches threads without dropping Reactor Context by default.
- `contextWrite` does not provide context to downstream operators outside its scope.
- `.cache()` on principal-dependent data creates cross-user leakage vulnerabilities.
- Composed async errors travel down the `onError` chain; errors from detached subscriptions generally do not surface in the request result.

## 6. Deep Dive into Code "Break Points"

### 6.1. `subscribe()` Hidden Inside `doOnNext`/`map`

**Wrong:**

```java
return repository.findById(id)
    .doOnNext(entity ->
        auditService.writeAsync(entity.getId()).subscribe())
    .map(Entity::getName);
```

**Right (mandatory audit):**

```java
return repository.findById(id)
    .flatMap(entity ->
        auditService.writeAsync(entity.getId())
            .thenReturn(entity.getName()));
```

In the right version, audit errors propagate back to the request; the wrong version spawns two independent subscriptions. If auditing is non-mandatory telemetry, use an explicit event-ingestion architecture (such as a message broker/outbox/dedicated worker) with retry/error policies and vetted identity fields passed explicitly. Never use detached `subscribe()` as an unreliable "queue".

### 6.2. `Mono.defer` Alone Is Not Enough If It Still Calls `subscribe()` Inside

**Wrong:**

```java
return Mono.defer(() -> {
    permissionService.checkCurrentUser().subscribe();
    return Mono.just("done");
});
```

`defer` delays Publisher creation until subscription time, yet the lambda still invokes a second `.subscribe()`. **Right:** return the composed chain:

```java
return Mono.defer(() ->
    permissionService.checkCurrentUser()
        .thenReturn("done"));
```

`Mono.deferContextual(ctx -> ...)` does not fix a nested `.subscribe()` either; it only reads the active subscriber's Context. Do not extract a `ContextView` containing full security state and pass it arbitrarily to external tasks; across async boundaries, pass **validated, permitted, minimally scoped values**.

### 6.3. Does `flatMap` Actually Lose Context?

In a normal Reactor chain:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .flatMap(authentication ->
        customerService.load(authentication.getName()));
```

`customerService.load` is subscribed by `flatMap`, so it can see the request Context unless it breaks the chain itself. If `load` internally runs `future.thenAccept(...); someMono.subscribe()`, the break lies **inside the service**, not in `flatMap`.

`subscribeOn`, `publishOn`, `delayElement`, and offloading to `Schedulers.boundedElastic()` via Reactor operators do not by default erase Reactor Context. By contrast, `new Thread`, `Executor.execute`, and `CompletableFuture.thenApply` are Java async APIs that do not understand Reactor Context automatically. Once bridged back into `Mono`/`Flux`, the **Reactor portion of the pipeline** can read Context, whereas code executing **inside the foreign callback** does not automatically share it. Never diagnose context loss solely from thread names in logs.

### 6.4. `then()`: Context Remains, Yet Do Not Place `contextWrite` on the Wrong Side

```java
Mono<String> wrong = Mono.just("start")
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth))
    .then(readCurrentUsername()); // readCurrentUsername is not upstream of contextWrite
```

```java
Mono<String> correct = Mono.just("start")
    .then(readCurrentUsername())
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));
```

This illustrates **operator scoping only**, assuming `auth` and `readCurrentUsername()` are already declared. In real apps, the framework populates the security context after authentication; never use `withAuthentication(auth)` to grant privileges arbitrarily to a request. Use `contextWrite` for deliberate test contexts or inside trusted security infrastructure.

### 6.5. `Mono.fromFuture`, `@Async`, and Raw `Executor`s

**Non-standalone illustration:** assume `legacyClient.callAsync(userId, action)` returns `CompletableFuture<Result>`:

```java
public Mono<Result> good(String action) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMap(authentication ->
            Mono.fromFuture(
                () -> legacyClient.callAsync(authentication.getName(), action)));
}
```

Extract the identity **inside the Context-bearing pipeline**, then pass the permitted username as an explicit argument into the async API. Never expect Java callbacks inside `CompletableFuture` to invoke `ReactiveSecurityContextHolder.getContext()` on their own, and avoid persisting full `Authentication` objects into job logs/queues unnecessarily. In multi-tenant systems, resolve the proper tenant/authorization when creating the request, and ensure receiving workers enforce their assigned checks.

If an external callback constructs a `Mono` and calls `.subscribe()`, it spawns a new subscriber. Using `Mono.fromFuture`/`Mono.create` properly to bridge the callback result into **one** Publisher and returning it lets callers stay composed in the request. With `Mono.create`, manage cancellation/resource cleanup and complete the sink safely—never signal success before the real callback finishes.

### 6.6. Servlet-Style `SecurityContextHolder` and MDC/ThreadLocal

In the Servlet stack, `SecurityContextHolder` defaults to a thread-bound strategy. WebFlux operates non-blockingly and can switch threads mid-pipeline. Calling `SecurityContextHolder.getContext()` in reactive services typically returns empty or wrong results. Use reactive APIs or principal injection instead.

Reactor 3.5+ integrates with Micrometer Context Propagation to **restore selected ThreadLocals that have registered accessors**, offering both a limited/default mode and an automatic mode (`Hooks.enableAutomaticContextPropagation()`). This mainly bridges Reactor Context and `ThreadLocal` (for tracing/MDC) per configuration; it is **not an automatic cure for detached `.subscribe()` calls**, nor does it justify abandoning `ReactiveSecurityContextHolder` or stuffing user permissions into global ThreadLocals.

If logs lose `traceId`/MDC while `ReactiveSecurityContextHolder` still sees authentication, that is a telemetry propagation issue distinct from losing `SecurityContext`. Avoid conflating the two under one hypothesis.

### 6.7. Custom `WebFilter` Running Too Early or Misplaced

A custom `WebFilter` running **before** Spring Security's filter populates the context will observe an empty context even when subsequent filters authenticate successfully. Inspect `SecurityWebFilterChain` setup, matchers, and effective filter order.

`WebFilter.filter(...)` must **return** a composed `Mono<Void>`, typically wrapping `chain.filter(exchange)`; never call `chain.filter(exchange).subscribe()` and return `Mono.empty()`. When inspecting `Authentication` in a filter, place it appropriately relative to the security filter chain, logging only sanitized diagnostic flags/names rather than full security objects or tokens.

### 6.8. `@PreAuthorize` and Side Effects Executed Outside the Protected Stream

Reactive method security relies on Reactor Context and fits methods returning `Mono`/`Flux`. If a security-annotated method triggers a side effect via a detached `.subscribe()` and immediately returns `Mono.empty()`, response completion and authorization checks on the returned chain **do not govern** that detached side effect. For privileged operations, always compose the work into the returned Publisher so security policies, errors, and cancellation apply along the intended path.

Never "solve" an empty context by fabricating a `UsernamePasswordAuthenticationToken` and calling `contextWrite(withAuthentication(...))` inside business services. Doing so can bypass real authentication and cause privilege escalation. When context is absent, fail closed per your authorization design.

## 7. Verifiable Step-by-Step Diagnostic Workflow

### Step 1 — Confirm Whether the Request Was Authenticated

Inspect the live endpoint: did the request carry a valid Bearer token/cookie, which `SecurityWebFilterChain` matched, did authentication succeed, or was `401`/`403`/redirect caused by authorization or CSRF rather than lost context? In tests, ensure `WebTestClient` applied security integration. **Never** assume every `Mono.empty()` stems from `.subscribe()`.

Inside a handler, a tightly scoped probe might look like:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(auth -> "authPresent=" + (auth != null))
    .defaultIfEmpty("authPresent=false");
```

This **snippet** only tells whether an `Authentication` object exists; `AnonymousAuthenticationToken` is also an `Authentication`, so distinguishing real users from anonymous requires checking token type/policy. Never log credentials, raw bearer tokens, or full `SecurityContext` objects.

### Step 2 — Map the Subscription Graph, Not Just the Call Stack

Along `handler → service → repository/client → callback`, record any occurrences of:

- `.subscribe(`, `.block(`, `.toFuture()`, `CompletableFuture.*Async`, `@Async`, `Executor.execute`, `new Thread`, or separately consumed `Sinks`.
- Unreturned `Mono` instances, or `.map`/`.doOnNext` calling a `Mono`-returning method without composing it.
- `.contextWrite(...)` appearing mid-chain; are the context-reading operators genuinely **upstream** of it?
- `cache()`, `share()`, `replay()`, or Publishers stored in singleton beans holding identity-dependent values.
- Custom `WebFilter`s or event listeners creating subscriptions outside the request lifecycle.

Quick visual map:

```text
request subscription + security context
  ├─ controller.flatMap(service) ------------ OK
  │    └─ repository.find().flatMap(audit) -- OK
  ├─ controller.doOnNext(v -> audit.subscribe())
  │                                      └── NEW subscriber, different default Context
  └─ handler -> executor.execute(callback)
                                         └── raw callback has no automatic Reactor Context
```

### Step 3 — Place "Probes" Before and After the Suspected Break

Insert temporary checks calling `ReactiveSecurityContextHolder.getContext()` **inside composed Publishers** to confirm context at the controller, service, before/after operators, inner Publishers, and execution callbacks. Example for test debugging:

```java
static Mono<String> probeUser(String stage) {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .defaultIfEmpty("<no-security-context>")
        .doOnNext(user -> System.out.println(stage + ": " + user));
}
```

This **snippet is for test environments**; logging usernames in production must follow your privacy policy. Attach it with `.flatMap(v -> probeUser("after-service").thenReturn(v))` so the probe participates in the pipeline. Never call `probeUser("stage").subscribe()` while debugging, because the probe itself would reproduce the exact detached-subscriber bug.

If a non-sensitive per-request marker is needed, attach `requestId` via `contextWrite(ctx -> ctx.put("requestId", id))` in a trusted integration layer and read it via `Mono.deferContextual(...)`. That marker helps distinguish subscriber contexts, yet **does not replace security identity** or prove security context stayed intact.

### Step 4 — Check Cancellation, Errors, and Completion Timing

Tasks launched via separate `.subscribe()` typically do not share request cancellation. A request may return 200 before auditing or permission checks finish, and async errors never reach the main pipeline's `doOnError`. When switching to `flatMap`/`then`, verify:

- The result emits **only after** mandatory work completes;
- Errors propagate or follow an explicit handling policy;
- Cancellation and time budgets behave as required;
- The task does not execute if the main stream is never subscribed.

Use `StepVerifier` to assert `expectNext`, `verifyComplete`, `expectErrorMatches`, and `verifyThenAssertThat` where needed, and use controlled schedulers/virtual time for async tests. Avoid `.block()` in production; use `.block()` in test fixtures only when truly sensible and never when it invalidates Context testing.

### Step 5 — Compare Two Requests with Two Distinct Identities

Exercise Alice and Bob **independently** through the same service or reusable Publisher to verify no stale cache, singleton state, or leftover `ThreadLocal` remains. If data is tenant-scoped, add cross-tenant checks: Bob's request must never see data resolved for Alice through a shared cached `Mono`.

### Step 6 — Remove Temporary Instrumentation and Keep Regression Tests

Strip temporary debug logging before production while keeping both the bug-reproducing and post-fix regression tests. For deeper diagnostics, Reactor provides `checkpoint("stage-name")` to tag assembly tracebacks and `Hooks.enableContextLossTracking()` in certain integrations where operators mishandle Context; note that these tools **do not catch every manual `subscribe()`** and carry overhead. Use controlled logs/metrics and never dump full Contexts, credentials, tokens, or personal data.

## 8. Verifying at the Spring Security WebFlux and `WebTestClient` Level

Unit tests with `contextWrite(withAuthentication(...))` in Section 5 prove Reactor mechanics, yet **do not prove** live production requests passed authentication. When integrating into a WebFlux app:

1. Ensure `SecurityWebFilterChain` protects the URLs with the right authentication mechanism (JWT, session, HTTP Basic, or OAuth2 Login per your system).
2. Test authenticated endpoints: `WebTestClient` uses `mockUser()` or `mockJwt()` via `spring-security-test` to verify context/authorization flow in tests. Those tests **simulate** authentication and do not test JWT signatures/issuers.
3. Test unauthenticated and under-privileged requests, confirming 401/403 or redirects per real policy.
4. For manual-`subscribe()` bugs, first write a test reproducing identity loss in the service, switch to composition, and assert the user appears at every layer. Test async errors and cancellation separately if critical.
5. If a `WebFilter` seems to run too early, trace filter ordering or isolate the filter in tests, adjust its position, and re-test.

**Illustrative snippet depending on `ApplicationContext` and configured Spring Security filters** (not a standalone Java file):

```java
WebTestClient client = WebTestClient.bindToApplicationContext(context)
    .apply(SecurityMockServerConfigurers.springSecurity())
    .build();

client.mutateWith(SecurityMockServerConfigurers.mockUser("alice"))
    .get()
    .uri("/api/whoami")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("alice");
```

Compiling requires imports for `WebTestClient`, `ApplicationContext`, and `SecurityMockServerConfigurers`, test-scoped `spring-security-test`, and an `/api/whoami` endpoint returning the username from `ReactiveSecurityContextHolder` inside the tested app.

**Keep this distinction clear:** `mockUser()`/`mockJwt()` verify Context and authorization inside the pipeline; to prove real Bearer decoding and signatures, send real tokens via `Authorization` against a real `ReactiveJwtDecoder` in integration tests. Never turn a Context-debugging exercise into an assumption that the JWT decoder is tested.

## 9. When Should Work Intentionally Be Detached from the Request?

Some business workflows require background work to continue after the HTTP response finishes. That introduces **a new trust boundary**: background tasks may no longer rely implicitly on the HTTP request's `ReactiveSecurityContextHolder`. Sound design:

- Inside the authenticated request, extract **permitted fields** (such as user ID, tenant ID, or action ID) along the reactive pipeline and enforce authorization before creating the job.
- Persist the event/job in a reliable system (outbox, message broker, or queue) with durable delivery and explicit error handling. Return `202 Accepted` only after the work is durably accepted per business rules.
- Consumers/workers operate under their own service identity, authorization policy, and signed/validated payload; if permissions can be revoked, re-check them at execution time as required.
- Define retries, dead-letter handling, idempotency, timeouts, auditing, correlation IDs, and sensitive-data boundaries. Avoid serializing entire `Authentication`/`SecurityContext` objects into messages.
- If a Reactor-compatible library genuinely needs context, establish it **explicitly via a trusted component** from verified identity/authorization rather than blindly copying request `SecurityContext` into long-lived background tasks.

Calling `auditService.record(...).subscribe()` in a controller provides **none** of the queuing, durability, authorization, or error handling above. If work must succeed synchronously with the business operation, compose it in the pipeline; if it is truly an independent async workflow, model that boundary explicitly.

## 10. Common Misconceptions and Errors

| Misconception / action | Why it is wrong | Proper approach |
| --- | --- | --- |
| "Switching threads with `publishOn` loses `SecurityContext`" | Reactor Context follows the subscriber, not the thread | Check first for detached subscriptions, mis-scoped `contextWrite`, or callback bridges |
| "A Publisher initialized in a bean field always lacks context" | Context is normally read at subscription time | Check whether it is composed vs. manually subscribed/cached/shared |
| "`Mono.defer()` automatically fixes context loss" | `defer` does not fix a nested `.subscribe()` | Remove manual subscribe and return a composed publisher |
| "`doOnNext(x -> service.save(x))` already saved it" | Creates a `Mono` with no subscriber | Use `flatMap(x -> service.save(x))` or `then(...)` |
| "I must call `.subscribe()` so WebFlux executes it" | Spring WebFlux subscribes to the Publisher returned by handlers/filters | Return `Mono`/`Flux` from controllers, services, and filters |
| "Use `.block()` to read username inside a reactive service" | Blocking plus separate subscription; can stall the event loop | Use reactive composition or principal injection |
| "`SecurityContextHolder` always reads the user like in MVC" | ThreadLocal is not WebFlux's Context contract | Use `ReactiveSecurityContextHolder` |
| "Enabling automatic ThreadLocal propagation is enough" | Bridges only ThreadLocals with accessors; does not attach detached subscribers | Verify Reactor Context and real boundaries |
| "If `getContext()` is empty, fall back to a default admin" | Bypasses authentication and enables privilege escalation | Keep deny-by-default; return error/anonymous per policy |
| "Testing with Alice alone is enough" | Shared caches/singletons can retain the first user | Cross-test Alice/Bob/tenants |
| "Request `doOnError` will catch background `.subscribe()` failures" | New subscriptions have separate lifecycles and error paths | Compose in pipeline or use a monitored queue/worker |
| "No auth present means the filter is broken" | Request may be unauthenticated or filter ran before auth | Check matching, filter ordering, and `401`/`403` statuses |

A subtler mistake: logging `"user=alice"` inside `doOnNext` and concluding downstream never loses Context. If an inner `flatMap` invokes a foreign callback that creates another subscription, Context can still be lost **after** that log point. Probe inside the Publisher at the suspected step under the exact subscriber.

## 11. Checklist Before Closing the Fix

1. On the reactive HTTP execution path, controllers, filters, and services **return** composed `Mono`/`Flux` publishers; no `.subscribe()`/`.block()` is used for business steps needing Context.
2. Unauthenticated requests are distinguished from lost Context; check status codes, `SecurityWebFilterChain`, filter order, anonymous auth, and real permissions.
3. Publishers constructed elsewhere are evaluated at **subscription time**; avoid singleton `cache()` holding per-user or per-tenant identity/data.
4. `contextWrite` has the proper upstream scope; no fake authentication is injected in business code to paper over errors.
5. Bridges to `CompletableFuture`, executors, and callback libraries return results into the pipeline while passing only permitted identity/tenant fields explicitly if callbacks need them.
6. JUnit tests cover detached `manual subscribe` context loss, proper `flatMap`, `publishOn`, `contextWrite` scope, multiple users, cache leakage, and async error propagation.
7. WebFlux integration tests prove context is accessible in real requests with configured authentication, testing against real auth methods where required.
8. User data and tokens never appear in Context logs; background tasks have dedicated security boundaries, retries, and auditing.
9. Context bugs are fixed at the **subscription break point**—never "fixed" by disabling authorization, dropping CSRF, or granting default privileges.

## Official Documentation

- Spring Security 6.5 — Reactive method security and `ReactiveSecurityContextHolder`: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security 6.5 — WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security API — `ReactiveSecurityContextHolder`: https://docs.spring.io/spring-security/site/docs/6.5.0/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Project Reactor — Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Project Reactor — From Reactive Programming to `subscribe()`: https://projectreactor.io/docs/core/release/reference/reactiveProgramming.html
- Project Reactor — Context Propagation Support: https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html
- Project Reactor — Testing with `StepVerifier`: https://projectreactor.io/docs/core/release/reference/testing.html
