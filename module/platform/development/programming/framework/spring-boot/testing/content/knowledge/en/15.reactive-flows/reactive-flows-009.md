# Testing Reactor Context and Scheduler Switching Boundaries

## 1. Objective

In Spring WebFlux, a request can pass through a `WebFilter`, controller, and service, then hop onto one or more worker threads via `subscribeOn` or `publishOn`. When carrying a `traceId`, correlation ID, or metadata tied to **a single subscription**, you should understand **Reactor Context** rather than assuming a `ThreadLocal` variable follows every thread.

This lesson answers two independent questions:

- **Context data:** which operators see which keys/values, when `Context` is created, and whether separate subscriptions leak data into one another?
- **Scheduler boundaries:** which thread runs source creation and operators before vs. after `subscribeOn` and `publishOn`, and does `Context` stay intact across a scheduler hop?

We will use Java 17+, Spring Boot 3.3.5, Reactor Core, JUnit Jupiter, `StepVerifier`, and `WebTestClient`. These versions are chosen for concrete examples, **not as a claim of the latest release**. A complete test suite verifies pure Reactor `Context`, thread names on dedicated schedulers, and HTTP headers flowing into `Context` through Spring WebFlux.

While reading, distinguish three concepts: **execution thread**, **subscriber context**, and **emitted `onNext` data**. They interact, yet do not replace one another.

## 2. What Is `Context`, and How Does It Differ from `ThreadLocal`?

`reactor.util.context.Context` stores key/value pairs attached to a subscription. Reactor exposes a read-only `ContextView` to many callbacks. `Context` offers an immutable API: `put` returns a new instance rather than mutating a shared map.

Example:

```java
Context original = Context.of("requestId", "R1");
Context changed = original.put("requestId", "R2");
// original.get("requestId") -> "R1"
// changed.get("requestId")  -> "R2"
```

This snippet requires importing `reactor.util.context.Context`. Note that immutability of the **`Context` container** does not make mutable objects stored inside it immutable or thread-safe.

| Criterion | Reactor Context | `ThreadLocal` |
| --- | --- | --- |
| Primary scope | Subscriber / reactive subscription | Java Thread |
| Reading | `Mono.deferContextual`, `ContextView` | `ThreadLocal.get()` |
| Writing | `contextWrite`, returns new `Context` | `ThreadLocal.set()` |
| Across `publishOn` thread hops | Reactor operators can still read matching `Context` | No automatic guarantee values follow |
| Common data leak | Cached emitted values or mishandled inner publishers | Pooled threads reused when `remove()` is forgotten |
| Role | Per-subscription metadata | Per-thread metadata |

**`Context` does not appear as an emitted value** unless an operator explicitly reads it. For example, `Mono.just("hello")` always emits `"hello"` regardless of `Context` contents; only `deferContextual` or context-aware operators turn metadata into output.

Never treat a `Context` key as a vault for passwords, raw tokens, or long-lived mutable business state. For tenant/authorization checks, data must originate from a trusted authentication mechanism; a client-supplied header alone is not sufficient to grant permissions.

## 3. Two Directions of a Reactive Chain: Subscription and Signals

An operator chain has two crucial directions:

```text
Assembly (reading source code):
Mono.deferContextual(...)
    .map(...)
    .publishOn(worker)
    .map(...)
    .contextWrite(Context.of("requestId", "R1"))

Subscription builds from downstream to upstream:
final subscriber
  ↑ contextWrite adds requestId
  ↑ map / publishOn / map
  ↑ deferContextual accesses requestId

onNext/onError/onComplete signals flow from source downward:
deferContextual → map → publishOn → map → subscriber
```

`contextWrite` modifies the `Context` propagated by the downstream subscriber to **operators upstream of it**. That is why placing it at the end of a chain usually lets operators above it read the data.

Simple example:

```java
Mono<String> p = Mono.deferContextual(
        ctx -> Mono.just("id=" + ctx.get("requestId")))
        .contextWrite(Context.of("requestId", "A"));
```

On subscription, the result is `id=A`.

### Changing Where `contextWrite` Sits Changes Its Meaning

```java
Mono<String> p = Mono.just("data")
        .contextWrite(Context.of("requestId", "A"))
        .flatMap(value -> Mono.deferContextual(
                ctx -> Mono.just(
                        ctx.getOrDefault("requestId", "missing"))));
```

The value produced by the downstream `flatMap` is `missing` if the final subscriber did not supply that key. `contextWrite` is not a command that "mutates a shared variable so lines below can see it".

### Two Segments of the Same Chain Can Read Two Different Values

```java
Mono<String> p = Mono.deferContextual(
                ctx -> Mono.just(ctx.<String>get("scope")))
        .contextWrite(ctx -> ctx.put("scope", "inner"))
        .flatMap(first -> Mono.deferContextual(
                ctx -> Mono.just(
                        first + "|" + ctx.<String>get("scope"))))
        .contextWrite(ctx -> ctx.put("scope", "outer"));
```

The result is `inner|outer`. `contextWrite("inner")` affects only operators upstream of it; the subsequent `flatMap` reads a `Context` containing `outer`.

**This is not a race condition.** Two intermediate subscribers intentionally observe different `Context` values because of how `Context` propagates.

## 4. Key APIs and How to Verify Them

| API | Purpose | Testing Notes |
| --- | --- | --- |
| `Context.of(k, v)` | Creates a `Context` | Ensure values have expected types |
| `Context.put(k, v)` | Returns a new `Context` with added/updated key | Original remains unchanged |
| `ContextView.get(k)` | Reads a required key | Missing key throws an exception |
| `ContextView.getOrDefault(k, fallback)` | Reads an optional key | Returns fallback when absent |
| `Mono.deferContextual(fn)` | Reads `Context` **at subscribe time** | Differs from reading state at assembly time |
| `Flux.deferContextual(fn)` | Same for multi-element streams | Watch ordering under `flatMap` |
| `contextWrite(ContextView)` | Merges downstream `Context` upstream | Operator position matters |
| `contextWrite(Function<Context, Context>)` | Transforms downstream `Context` | Must return a new `Context` |
| `transformDeferredContextual(fn)` | Builds a transformation with `Context` access | Triggered on subscription |
| `StepVerifierOptions.withInitialContext` | Supplies initial `Context` to verifier | Tests publishers without adding `contextWrite` |
| `StepVerifier.expectAccessibleContext` | Asserts `Context` is accessible in chain | Call `then()` to return to `onNext` assertions |
| `StepVerifier.expectNoAccessibleContext` | Asserts no accessible `Context` exists | Use only when that is the contract |

When a `Context` key is required:

```java
Mono<String> reader = Mono.deferContextual(
        ctx -> Mono.just(ctx.<String>get("requestId")));
```

If the subscriber lacks that key, `ctx.get` throws `NoSuchElementException`, which Reactor converts into an **error signal** on subscription. Test it with `StepVerifier.expectError` rather than wrapping `Mono` creation in `assertThrows`, since the source does not execute at assembly time.

## 5. Choosing the Right Test Scope

For this topic, **no Spring Boot context is needed** to prove `Context` or schedulers behave as intended. Pure Reactor unit tests using `StepVerifier` and test-owned schedulers are the right choice. However, to verify that a `WebFilter` is registered by Spring and HTTP headers enter `Context`, you need an integrated WebFlux test.

| Goal | How to Test |
| --- | --- |
| Does `contextWrite` reach upstream operators? | `StepVerifier.expectNext` |
| Are subscriptions A and B's `Context` isolated? | Create two `StepVerifier` runs on the same cold source |
| Does a missing key become an error signal? | `StepVerifier.expectError` |
| Can subscribers supply an initial `Context`? | `StepVerifierOptions.withInitialContext` |
| Which thread does `subscribeOn` run the source on? | `Mono.fromSupplier` + named `Scheduler` |
| Does `publishOn` switch downstream operators? | Capture thread names before and after boundary |
| Does Reactor `Context` survive a scheduler hop? | `deferContextual` before/after hop, assert values |
| Does WebFlux filter copy request header into `Context`? | `@SpringBootTest(RANDOM_PORT)` + `WebTestClient` |
| Do MDC/`ThreadLocal` bridge across threads? | Separate test with real Micrometer context-propagation setup |

Never replace terminal-signal checks with `Thread.sleep`; `StepVerifier` awaits completion or errors with a timeout. Never use `withVirtualTime` to prove worker-thread hops: virtual time handles timers rather than real thread boundaries.

## 6. Runnable Java 17+ Example Project

Structure:

```text
reactor-context-boundary/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/context/
│   ├── ContextBoundaryApplication.java
│   ├── RequestIdFilter.java
│   └── TraceController.java
└── src/test/java/com/example/context/
    ├── ContextRulesTest.java
    ├── SchedulerBoundaryTest.java
    └── TraceHttpTest.java
```

### 6.1. `settings.gradle`

```groovy
rootProject.name = 'reactor-context-boundary'
```

### 6.2. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

`spring-boot-starter-webflux` selects the reactive web stack. Do not add `spring-boot-starter-web` to the sample project, because when both MVC and WebFlux sit on the classpath, Boot typically prefers Servlet MVC unless the web application type is explicitly overridden. `reactor-test` provides `StepVerifier`; Reactor Core is managed by the Spring Boot BOM.

`./gradlew` commands work when the project includes a **Gradle Wrapper**. Without a wrapper, use a compatible `gradle` installation. Java 17+ is the minimum requirement for the sample app.

### 6.3. Spring Boot Application

Create `src/main/java/com/example/context/ContextBoundaryApplication.java`:

```java
package com.example.context;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContextBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(ContextBoundaryApplication.class, args);
    }
}
```

## 7. Spring WebFlux Filter Storing Request ID in Reactor Context

`src/main/java/com/example/context/RequestIdFilter.java`:

```java
package com.example.context;

import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class RequestIdFilter implements WebFilter {

    public static final String TRACE_ID = "traceId";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String incoming = exchange.getRequest()
                .getHeaders()
                .getFirst("X-Request-Id");

        String resolved = (incoming == null || incoming.isBlank())
                ? "none"
                : incoming;

        return chain.filter(exchange)
                .contextWrite(ctx -> ctx.put(TRACE_ID, resolved));
    }
}
```

The filter does not use static fields or `ThreadLocal` to store `traceId`. It extracts the header for the current request and uses `contextWrite` to supply `Context` to the handler chain's subscription.

### Why Write `chain.filter(exchange).contextWrite(...)`?

`WebFilterChain.filter(...)` returns a `Mono<Void>` representing the remainder of WebFlux processing. When subscribed, `contextWrite` sets the key upstream in the chain so context-aware operators and handlers can read it.

Calling `contextWrite` on an **unrelated** `Mono` and then returning a different `chain.filter(exchange)` loses the `Context`, because the unsubscribed `Mono` has no effect. That is a common wiring mistake: `Context` binds to a **subscription**, not global mutable state.

If your app performs authentication, never trust client-controlled headers as tenant or role claims inside `Context` for authorization decisions. The `X-Request-Id` header here carries **correlation metadata** only, and `"none"` is a teaching fallback.

## 8. Controller Reading `Context` After a Scheduler Hop

`src/main/java/com/example/context/TraceController.java`:

```java
package com.example.context;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
public class TraceController {

    @GetMapping(
            value = "/trace",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> trace() {
        return Mono.just("ready")
                .publishOn(Schedulers.parallel())
                .flatMap(ignored -> Mono.deferContextual(ctx ->
                        Mono.just("trace=" + ctx.getOrDefault(
                                RequestIdFilter.TRACE_ID, "none"))));
    }
}
```

Here `publishOn(Schedulers.parallel())` is an intentional hop for learning purposes. `deferContextual` sits inside `flatMap` downstream of the hop, so the endpoint reads `Context` **after the signal switched schedulers**. The HTTP test in Section 11 checks the response; the scheduler test in Section 10 checks explicit thread names.

Do not sprinkle `publishOn` onto every production endpoint: thread hops add overhead and can hurt locality. With genuine reactive drivers, most flows need no manual scheduling. Use `Schedulers.parallel` for non-blocking CPU work when appropriate, and `Schedulers.boundedElastic` to isolate unavoidable blocking calls.

## 9. `ContextRulesTest` Suite: 7 Independent Scenarios

Create `src/test/java/com/example/context/ContextRulesTest.java`:

```java
package com.example.context;

import java.time.Duration;
import java.util.NoSuchElementException;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.util.context.Context;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ContextRulesTest {

    private static final String TRACE_ID = "traceId";

    @Test
    void contextWriteMakesValueVisibleToUpstream() {
        Mono<String> source = Mono.deferContextual(
                ctx -> Mono.just("trace=" +
                        ctx.<String>get(TRACE_ID)))
                .contextWrite(Context.of(TRACE_ID, "r-100"));

        StepVerifier.create(source)
                .expectNext("trace=r-100")
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void separateSubscriptionsUseSeparateContext() {
        Mono<String> reader = Mono.deferContextual(
                ctx -> Mono.just(
                        ctx.getOrDefault(TRACE_ID, "missing")));

        StepVerifier.create(reader.contextWrite(
                        Context.of(TRACE_ID, "request-A")))
                .expectNext("request-A")
                .verifyComplete();

        StepVerifier.create(reader.contextWrite(
                        Context.of(TRACE_ID, "request-B")))
                .expectNext("request-B")
                .verifyComplete();

        StepVerifier.create(reader)
                .expectNext("missing")
                .verifyComplete();
    }

    @Test
    void contextWriteDoesNotPropagateDownstream() {
        Mono<String> source = Mono.just("data")
                .contextWrite(Context.of(TRACE_ID, "upstream-only"))
                .flatMap(value -> Mono.deferContextual(ctx ->
                        Mono.just(
                                ctx.getOrDefault(TRACE_ID, "missing"))));

        StepVerifier.create(source)
                .expectNext("missing")
                .verifyComplete();
    }

    @Test
    void nestedAndOuterContextMayDiffer() {
        Mono<String> source = Mono.deferContextual(
                        ctx -> Mono.just(ctx.<String>get("scope")))
                .contextWrite(ctx -> ctx.put("scope", "inner"))
                .flatMap(first -> Mono.deferContextual(
                        ctx -> Mono.just(
                                first + "|" + ctx.<String>get("scope"))))
                .contextWrite(ctx -> ctx.put("scope", "outer"));

        StepVerifier.create(source)
                .expectNext("inner|outer")
                .verifyComplete();
    }

    @Test
    void verifierSuppliesInitialContext() {
        Mono<String> source = Mono.deferContextual(
                ctx -> Mono.just("tenant=" +
                        ctx.<String>get("tenantId")));

        StepVerifier.create(
                        source,
                        StepVerifierOptions.create().withInitialContext(
                                Context.of("tenantId", "tenant-A")))
                .expectAccessibleContext()
                .contains("tenantId", "tenant-A")
                .then()
                .expectNext("tenant=tenant-A")
                .verifyComplete();
    }

    @Test
    void missingRequiredKeyProducesErrorSignal() {
        Mono<String> source = Mono.deferContextual(
                ctx -> Mono.just(ctx.<String>get(TRACE_ID)));

        StepVerifier.create(source)
                .expectError(NoSuchElementException.class)
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void putReturnsNewContextInsteadOfMutatingSource() {
        Context original = Context.of(TRACE_ID, "before");
        Context changed = original.put(TRACE_ID, "after");

        assertEquals("before", original.get(TRACE_ID));
        assertEquals("after", changed.get(TRACE_ID));
    }
}
```

### Explanation of Each Test

**`contextWriteMakesValueVisibleToUpstream`** checks that `Context` written downstream of `deferContextual` flows up and produces the right value. No real HTTP thread is involved.

**`separateSubscriptionsUseSeparateContext`** reuses the same cold `Mono` across three subscriptions. Subscriber A gets `request-A`, subscriber B gets `request-B`, and the key-less subscriber gets `missing`. If someone stored request IDs in a static field, a similar test exposes state leakage.

**`contextWriteDoesNotPropagateDownstream`** enforces Context propagation direction. A `contextWrite` does not affect a `flatMap` positioned downstream in the same chain.

**`nestedAndOuterContextMayDiffer`** verifies two sections of a chain see distinct `Context` values legitimately, rather than behaving like one shared mutable map.

**`verifierSuppliesInitialContext`** uses `StepVerifierOptions.withInitialContext` to simulate subscriber-supplied `Context`. `expectAccessibleContext().contains(...).then()` checks context accessibility before asserting emitted items. Both checks add value: having a key in `Context` does not guarantee business code actually used the right key.

**`missingRequiredKeyProducesErrorSignal`** demonstrates that a missing required `traceId` becomes `onError` at subscribe time. Because `Mono.deferContextual` is lazy, do not wrap `Mono` construction in `assertThrows`.

**`putReturnsNewContextInsteadOfMutatingSource`** checks `Context` immutability. This is a plain JUnit assertion needing no subscriber.

**Expected result:** 7 test methods. These methods were not executed in this session; run Gradle in your environment to verify.

## 10. `SchedulerBoundaryTest` Suite: Thread Boundaries and `Context`

Create `src/test/java/com/example/context/SchedulerBoundaryTest.java`:

```java
package com.example.context;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SchedulerBoundaryTest {

    @Test
    void subscribeOnMovesSourceEvaluation() {
        Scheduler worker = Schedulers.newSingle("source-boundary");
        AtomicReference<String> sourceThread = new AtomicReference<>();
        AtomicReference<String> mapThread = new AtomicReference<>();

        try {
            Mono<Integer> p = Mono.fromSupplier(() -> {
                        sourceThread.set(
                                Thread.currentThread().getName());
                        return 5;
                    })
                    .map(value -> {
                        mapThread.set(
                                Thread.currentThread().getName());
                        return value * 2;
                    })
                    .subscribeOn(worker);

            StepVerifier.create(p)
                    .expectNext(10)
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));

            assertNotNull(sourceThread.get());
            assertTrue(sourceThread.get()
                    .startsWith("source-boundary-"));
            assertEquals(sourceThread.get(), mapThread.get());
        } finally {
            worker.dispose();
        }
    }

    @Test
    void publishOnMovesDownstreamButNotPreviousSource() {
        Scheduler worker = Schedulers.newSingle("downstream-boundary");
        AtomicReference<String> before = new AtomicReference<>();
        AtomicReference<String> after = new AtomicReference<>();
        String testThread = Thread.currentThread().getName();

        try {
            Mono<Integer> p = Mono.just(7)
                    .doOnNext(value -> before.set(
                            Thread.currentThread().getName()))
                    .publishOn(worker)
                    .map(value -> {
                        after.set(Thread.currentThread().getName());
                        return value + 1;
                    });

            StepVerifier.create(p)
                    .expectNext(8)
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));

            assertEquals(testThread, before.get());
            assertNotNull(after.get());
            assertTrue(after.get().startsWith(
                    "downstream-boundary-"));
        } finally {
            worker.dispose();
        }
    }

    @Test
    void contextSurvivesSubscribeOnAndPublishOn() {
        Scheduler source = Schedulers.newSingle("ctx-source");
        Scheduler downstream = Schedulers.newSingle("ctx-after");
        AtomicReference<String> onSource = new AtomicReference<>();
        AtomicReference<String> onDownstream = new AtomicReference<>();

        try {
            Mono<String> p = Mono.deferContextual(ctx -> {
                        onSource.set(Thread.currentThread().getName());
                        return Mono.just(ctx.<String>get("traceId"));
                    })
                    .subscribeOn(source)
                    .publishOn(downstream)
                    .flatMap(id -> Mono.deferContextual(ctx -> {
                        onDownstream.set(
                                Thread.currentThread().getName());
                        return Mono.just(id + "|" +
                                ctx.<String>get("traceId"));
                    }))
                    .contextWrite(Context.of("traceId", "req-900"));

            StepVerifier.create(p)
                    .expectNext("req-900|req-900")
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));

            assertNotNull(onSource.get());
            assertNotNull(onDownstream.get());
            assertTrue(onSource.get().startsWith("ctx-source-"));
            assertTrue(onDownstream.get().startsWith("ctx-after-"));
        } finally {
            source.dispose();
            downstream.dispose();
        }
    }

    @Test
    void eachPublishOnCreatesAnotherBoundary() {
        Scheduler first = Schedulers.newSingle("stage-one");
        Scheduler second = Schedulers.newSingle("stage-two");
        AtomicReference<String> stageOne = new AtomicReference<>();
        AtomicReference<String> stageTwo = new AtomicReference<>();

        try {
            Mono<String> p = Mono.just("ok")
                    .publishOn(first)
                    .map(text -> {
                        stageOne.set(Thread.currentThread().getName());
                        return text;
                    })
                    .publishOn(second)
                    .map(text -> {
                        stageTwo.set(Thread.currentThread().getName());
                        return text.toUpperCase();
                    });

            StepVerifier.create(p)
                    .expectNext("OK")
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));

            assertNotNull(stageOne.get());
            assertNotNull(stageTwo.get());
            assertTrue(stageOne.get().startsWith("stage-one-"));
            assertTrue(stageTwo.get().startsWith("stage-two-"));
        } finally {
            first.dispose();
            second.dispose();
        }
    }
}
```

**Expected result:** 4 test methods.

### `subscribeOn` Is a Boundary for Source and Subscription

In the first test, `Mono.fromSupplier` runs upon subscription. `subscribeOn(worker)` shifts subscription and source evaluation to a scheduler whose thread starts with `source-boundary-`. The `map` right after the source also runs on that worker until another scheduler-switching operator appears.

Do not claim `subscribeOn` affects only the single source line: it governs subscription and carries downstream callbacks along on the same thread unless a `publishOn` changes it.

### `publishOn` Is a Boundary for Downstream Signals

The second test uses `Mono.just(7)` which emits synchronously on the JUnit thread in this setup. `doOnNext` before `publishOn` captures the JUnit thread, while `map` after `publishOn(worker)` captures the new worker. Checking both before and after proves the boundary sits in the right place.

Do not place `publishOn` at the bottom expecting an upstream `map` above it to run on the new thread: it affects downstream **after** the boundary.

### `Context` Is Not Tied to Thread Names

The third test verifies `Context` `req-900` is read at two stages while confirming those two stages ran on threads with distinct prefixes. When `Context` stays intact across `subscribeOn` and `publishOn`, you have proof of **Reactor `Context` propagation across that chain**. Do not generalize this to mean every `ThreadLocal` preserves the same data.

### Resilient Thread Assertions

`Schedulers.newSingle("prefix")` gives tests dedicated scheduler thread prefixes. Assert `startsWith("prefix-")` rather than matching exact global names like `"parallel-1"` or JVM-wide thread numbers. Shared pool thread names vary by environment, version, and parallel suites.

`AtomicReference` safely passes captured values across threads; the test only reads them after `StepVerifier` observes the terminal signal. Always `dispose()` test-created schedulers in `finally` to avoid leaking worker threads.

### Why Avoid `Thread.sleep`?

A test like:

```java
publisher.subscribe(value -> observed.set(value));
Thread.sleep(100);
assertEquals("ok", observed.get());
```

is an **anti-pattern snippet** with undefined variables. Waiting a fixed interval does not guarantee the publisher finished; slow CI runners make it flaky. Use `StepVerifier` to subscribe, assert `onNext`/`onError`/`onComplete`, and add `verify(Duration.ofSeconds(5))` as an explicit bound.

## 11. Integration Test: HTTP Header Passing Through `WebFilter` into Reactor `Context`

Create `src/test/java/com/example/context/TraceHttpTest.java`:

```java
package com.example.context;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class TraceHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void requestHeaderIsVisibleAfterSchedulerHop() {
        client.get()
                .uri("/trace")
                .header("X-Request-Id", "trace-123")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("trace=trace-123");
    }

    @Test
    void twoRequestsHaveIndependentContext() {
        client.get()
                .uri("/trace")
                .header("X-Request-Id", "request-A")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("trace=request-A");

        client.get()
                .uri("/trace")
                .header("X-Request-Id", "request-B")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("trace=request-B");

        client.get()
                .uri("/trace")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("trace=none");
    }
}
```

**Expected result:** 2 test methods.

This class starts an embedded WebFlux HTTP server on an OS-assigned port rather than hardcoding a port. `WebTestClient` sends real requests, the filter is registered via Spring component scan, and the controller reads `Context` **after `publishOn`**. This tests the boundary from **HTTP header → `WebFilter` → Reactor `Context` → controller**.

`WebTestClient` can also run in mock binding mode with `@WebFluxTest`. Here `RANDOM_PORT` is chosen to exercise the request through a live server. Pure Reactor unit tests in Sections 9–10 are faster and should cover most `Context`/scheduler rules; HTTP tests cover real wiring.

### Preventing Data Leaks Across Requests

The second test sends A, B, and a headerless request; a buggy singleton bean storing `requestId` in a field would leak state and fail this test. Still, sequential calls cannot catch all concurrency races under load. When production requires high-concurrency isolation guarantees, add an integration test firing concurrent requests with distinct IDs and asserting each response receives its own ID.

`Context` is subscription-scoped, yet if code places an ID inside **a globally cached emitted value**, data still leaks via the cache. Therefore, context isolation tests should cover hot/shared publishers whenever an app uses `cache()`, `share()`, or `replay()`.

## 12. Running Tests and Reading Reports Properly

| Class | Methods | Role |
| --- | ---: | --- |
| `ContextRulesTest` | 7 | Propagation direction, immutable `Context`, initial `Context`, isolation, and error |
| `SchedulerBoundaryTest` | 4 | `subscribeOn`/`publishOn`, thread names, and keeping `Context` across hops |
| `TraceHttpTest` | 2 | WebFlux HTTP filter and `Context` from request headers |

Total of **13 `@Test` methods** in the sample code.

Run with:

```bash
./gradlew test --tests "com.example.context.ContextRulesTest"
./gradlew test --tests "com.example.context.SchedulerBoundaryTest"
./gradlew test --tests "com.example.context.TraceHttpTest"
./gradlew test
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
```

If there is no Wrapper and a compatible Gradle is installed, run `gradle test`. Expected result is PASS, though **only an actual execution report confirms it**. Tests produce no fixed business stdout. Check the Gradle HTML report at `build/reports/tests/test/index.html` or XML under `build/test-results/test`.

If a scheduler test fails, diagnose whether the root cause is emitted value, thread prefix, timeout, or lifecycle; do not adjust expected threads to match arbitrary environment names. If an HTTP test fails, check web application type (WebFlux vs. MVC), filter bean registration, headers, ports, and server logs.

## 13. `Context` and MDC/`ThreadLocal`: Do Not Conflate Them

In traditional Spring MVC apps, developers often call `MDC.put("traceId", value)` and log on the request thread. In WebFlux, operators can run on an event-loop thread and then hop to a worker thread.

`ThreadLocal` is bound to a thread and does not automatically read from Reactor `Context`. If a filter populates MDC before the publisher runs, a worker after `publishOn` may see `null` or stale state. Because schedulers reuse threads across requests, forgetting to clear `ThreadLocal` can even expose an earlier request's ID.

Reactor Core integrates with Micrometer `io.micrometer:context-propagation` (from Reactor 3.5+). With `ThreadLocalAccessor` adapters and proper propagation modes, supported `ThreadLocal` values can be restored from `Context` across supporting operators; automatic propagation can be enabled via `Hooks.enableAutomaticContextPropagation()` depending on version and setup.

**Never enable global hooks casually in a test and forget to disable/reset them.** Global hooks affect every subsequent subscription in the JVM/suite. If your app relies on Boot Observability/Tracing, write dedicated tests against the real Micrometer/SLF4J/OpenTelemetry stack, because pure Reactor `Context` tests **do not prove MDC is bridged**.

A solid MDC test checks two requests with distinct IDs plus a request without an ID across scheduler hops, inspects the logged context on the worker thread, and verifies cleanup after completion, error, and cancellation—without relying on the first and second requests landing on the same thread.

## 14. `flatMap`, Inner Publishers, and `Context` Boundaries

`flatMap` creates inner subscriptions. Reactor-native operators propagate `Context`, yet a `contextWrite` **inside an inner chain does not modify the outer chain's `Context`**.

Example:

```java
Mono<String> p = Mono.just("order-1")
        .flatMap(id -> Mono.deferContextual(
                ctx -> Mono.just(id + ":" +
                        ctx.<String>get("scope")))
                .contextWrite(Context.of("scope", "inner")))
        .flatMap(first -> Mono.deferContextual(
                ctx -> Mono.just(first + ":" +
                        ctx.getOrDefault("scope", "missing"))));
```

This produces `order-1:inner:missing` when the outer subscriber provides no `scope` key. `"inner"` attaches to the inner publisher only and does not leak outward to alter the subsequent `flatMap`'s `Context`.

With `Flux.flatMap` running multiple inner publishers concurrently, emission order is not fixed. When order is not part of the contract, assert the collection/count instead of `expectNext(a, b, c)`. When order is required, consider `concatMap` or `flatMapSequential` and verify latency/order per their semantics.

### Creating Subscriptions with `subscribe()` Inside a Callback

Anti-pattern:

```java
Mono.just("start")
    .doOnNext(value -> anotherPublisher.subscribe())
    .contextWrite(Context.of("traceId", "r-1"));
```

`anotherPublisher` is an illustrative variable from an outer scope. Calling `subscribe()` starts a detached subscription that does not automatically inherit the outer subscriber's `Context`; errors and cancellation of that inner subscription are also disconnected from the main pipeline.

The right pattern is usually **composition**:

```java
Mono.just("start")
    .flatMap(value -> anotherPublisher)
    .contextWrite(Context.of("traceId", "r-1"));
```

With the appropriate `Mono` signature, `flatMap` chains lifecycle, error propagation, and `Context` instead of firing off an unmanaged subscription. Never call `subscribe()` inside services just to "make the publisher run".

## 15. Boundaries Outside Reactor

`CompletableFuture.supplyAsync`, custom executors, plain Java callbacks, and libraries spawning their own threads know nothing about Reactor `Context`. When bridging from `Mono` to external APIs and back, decide explicitly how metadata is carried:

- Explicit arguments (`requestId` passed into the adapter) whenever simple and safe.
- A registered context snapshot/adapter via the appropriate SPI.
- API design where an outer Reactor operator reads `Context` and forwards data into the external call.

Never assume `Mono.fromFuture` lets code inside `CompletableFuture` read Reactor `Context`. It only bridges the Future's completion signal back into the reactive stream; Future callbacks already executed under their own executor's rules.

### Cached and Hot Publishers

`Mono.deferContextual` lets each subscription read `Context` at subscribe time. However, if you write:

```java
Mono<String> shared =
        Mono.deferContextual(ctx ->
                Mono.just(ctx.<String>get("traceId")))
            .cache();
```

the `shared` publisher caches the value emitted by the first subscription. A second subscriber with a different `Context` still receives the cached value from the first subscriber. That is a leak via **cached output**, not immutable Reactor `Context` turning into a shared map. Never cache publishers carrying per-request metadata as global singletons.

## 16. Virtual Time, Timeouts, and Thread Boundaries

`StepVerifier.withVirtualTime` suits `delayElements`, `timeout`, and `retryWhen` with backoff. Virtual time replaces real waiting with simulated scheduler clocks for operators constructed at the right time.

Illustrative example:

```java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofHours(2)))
    .expectSubscription()
    .expectNoEvent(Duration.ofHours(2))
    .expectNext(0L)
    .verifyComplete();
```

Requires `Mono`, `StepVerifier`, and `Duration` imports. This test does not sleep for two real hours. However, the virtual-time scheduler **is not a tool to prove callbacks ran on real worker threads**, because it uses a special scheduling model. To verify `subscribeOn`/`publishOn` thread boundaries, use dedicated `Schedulers.newSingle` instances as in Section 10.

`verifyComplete()` does not enforce a timeout suitable for all environments. For tests involving scheduler hops, use `expectComplete().verify(Duration.ofSeconds(5))` or a CI-appropriate budget so hung publishers fail rather than stalling forever.

## 17. Blocking I/O in a Reactive Chain

Returning a `Mono` does not automatically make everything inside non-blocking. A controller running synchronous JDBC before calling `Mono.just(...)` still blocks the request thread. `Schedulers.parallel()` has few workers suited for non-blocking CPU work and **must not execute slow blocking I/O**.

For legacy blocking dependencies that must temporarily remain, a common pattern is:

```java
Mono.fromCallable(() -> legacyRepository.load(id))
        .subscribeOn(Schedulers.boundedElastic());
```

This is an illustrative snippet with application-defined `legacyRepository` and `id`, not part of the runnable project. `boundedElastic` isolates bounded blocking calls off event-loop threads; it **does not turn blocking I/O into non-blocking I/O**.

If a blocking adapter needs the request ID, read Reactor `Context` inside the reactive pipeline and pass the ID explicitly to the adapter, or configure context propagation. Never expect a `ThreadLocal` set on an event-loop thread to magically appear on a `boundedElastic` thread.

## 18. Common Mistakes

| Error or Symptom | Cause | Testing / Fix |
| --- | --- | --- |
| `NoSuchElementException` from `ContextView.get` | Missing key | Place `contextWrite` properly downstream, or use intentional fallback |
| Source sees `Context`, downstream operator does not | `contextWrite` only affects upstream | Check operator order and each stage's `Context` |
| Second `flatMap` misses key written in first inner | Inner `Context` does not escape to outer chain | Write `Context` on outer chain or pass data explicitly |
| `ThreadLocal`/MDC is `null` after hop | Missing propagation adapter | Use Reactor `Context` or version-matched Micrometer bridge |
| Verification finishes before completion | Unawaited async `subscribe` | Use `StepVerifier` + timeout, never `sleep` |
| Test asserting `"parallel-1"` flakes | Shared thread pool used by other suites | Use test-owned schedulers with unique prefixes |
| Test hangs | Non-terminating publisher or unbounded retries | Add timeout, inspect signal lifecycle |
| Request A sees B's ID | Static/singleton mutable state or cached outputs | Test multiple distinct request `Context`s |
| `Context.put` expected to mutate original | Immutable API | Assign and return the new `Context` |
| `subscribeOn` assumed to move only one source line | Subscription scheduling covers downstream operators too | Capture threads at both source and `map` |
| `publishOn` assumed to move upstream operators | It governs downstream signals only | Capture threads before and after boundary |
| `Context` is right, log trace is wrong | Reactor `Context` and MDC are separate systems | Write dedicated logging/bridge tests |
| Virtual-time test asserts real thread names | Virtual time tests timers | Use real named schedulers for hop tests |
| `CompletableFuture` callback loses ID | Outside Reactor without a bridge | Pass explicit args or context snapshot |
| `cache()` shared across per-request `Mono` | Cached `onNext` exposes first request's value | Never share cached values containing per-request metadata |
| Scheduler tests leak threads | Newly created `Scheduler` not disposed | Wrap with `try/finally` and `dispose()` |
| Full HTTP tests too slow | Booting Spring context for pure Reactor rules | Separate unit tests from integration tests |
| Test checks only HTTP status | Cannot tell if `Context` value was right | Assert response body across multiple request IDs |

## 19. Practical Checklist

Before merging tests:

1. Are the `Context` key/value and single-subscription scope clearly defined?
2. Does code read `Context` via `deferContextual` at subscribe time rather than locking data at assembly time?
3. Is `contextWrite` placed downstream of the operators reading it?
4. Are missing keys and fallback/error paths tested when applicable?
5. Do two subscriptions to the same cold publisher receive isolated `Context` values?
6. Is `StepVerifierOptions.withInitialContext` used when modeling subscriber-supplied context?
7. Does `expectAccessibleContext` chain `then()` and assertions on emitted values?
8. Does the `subscribeOn` test capture the actual source thread?
9. Does the `publishOn` test capture both pre-hop and post-hop operators?
10. When multiple `publishOn` operators exist, are callbacks verified after each boundary?
11. Does `Context` remain intact across each hop independently of thread names?
12. Do tests use dedicated named schedulers rather than asserting shared pool worker numbers?
13. Do tests wait for terminal signals with sensible timeouts?
14. Are newly created schedulers disposed in `finally`?
15. Are Reactor `Context` and MDC/`ThreadLocal` kept distinct, with bridge tests added when required?
16. Are stray `subscribe()` calls avoided inside `doOnNext`/`map`?
17. Are singleton cached publishers avoided for request-dependent outputs?
18. When testing HTTP wiring, does `WebTestClient` run against the real WebFlux runtime?
19. Do two requests with different IDs and one without an ID yield distinct expected responses?
20. Is it guaranteed that client headers are never trusted as authorization claims?
21. Does production code avoid blocking event loops and choose appropriate schedulers?
22. Was Gradle run in the target environment to observe actual PASS/FAIL outcomes rather than counting `@Test` methods in source?

## 20. Reinforcement Exercises

1. Move `contextWrite` in `contextWriteMakesValueVisibleToUpstream` and predict where `get` will throw.
2. Replace `get("traceId")` with `getOrDefault("traceId", "missing")` and compare the error signal with the fallback behavior.
3. Add a fourth subscription with key `request-C` to `separateSubscriptionsUseSeparateContext`.
4. Remove `withInitialContext` in `verifierSuppliesInitialContext` and explain which assertion step fails first.
5. In `subscribeOnMovesSourceEvaluation`, remove `subscribeOn` and check which thread runs the source.
6. In `publishOnMovesDownstreamButNotPreviousSource`, move `publishOn` to the very end of the chain; identify which callbacks still run on the JUnit thread.
7. Add a second `publishOn` into a context-bearing pipeline and verify both `Context` values and thread prefixes.
8. Create a shared `Mono.deferContextual(...).cache()`, subscribe with two different `Context`s, and distinguish cached output from subscriber `Context`.
9. Try calling `subscribe()` inside a callback and compare it with composing via `flatMap`.
10. Run the HTTP test with two distinct request IDs; if data leaks, inspect static fields/caches before blaming `Context`.
11. In an app using Micrometer context-propagation, write a dedicated test checking MDC after a scheduler hop.
12. Write a test handling `Mono.error(...)` under a `Context` with a trace ID; verify the error signal and ensure logging metadata does not leak into the HTTP response.
13. Sandbox a blocking adapter with `boundedElastic` and verify it does not run on an event-loop thread; avoid sleeps in production.
14. Use `StepVerifier.withVirtualTime` to verify a retry delay; explain why that differs from a thread-boundary test.

## 21. References

- [Project Reactor 3.6 — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/3.6.17/reference/#context): `Context`, `ContextView`, `contextWrite`, `deferContextual`.
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/3.6.17/reference/#schedulers): `subscribeOn`, `publishOn`, `Schedulers`.
- [Project Reactor — Testing a Context](https://projectreactor.io/docs/core/3.6.17/reference/#_testing_the_context): `StepVerifierOptions.withInitialContext`, `expectAccessibleContext`.
- [Project Reactor — Context Propagation Support](https://projectreactor.io/docs/core/3.6.17/reference/#context-propagation-support): Micrometer SPI, `ThreadLocal` bridging.
- [Spring Framework — WebFlux WebFilter](https://docs.spring.io/spring-framework/reference/web/webflux-webhandler-api.html): `WebHandler`/`WebFilter` chain.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): testing WebFlux with or without a live HTTP server.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): WebFlux testing and `RANDOM_PORT`.

## 22. Summary

**Reactor `Context` travels with a subscription, not a Java thread.** `contextWrite` transforms `Context` for upstream operators; `deferContextual` reads `Context` at subscribe time; `StepVerifierOptions.withInitialContext` lets tests supply subscriber `Context`. Verify both aspects: visible `Context` values and isolation across separate subscriptions.

`subscribeOn` schedules subscription and source execution, while `publishOn` switches downstream signal handling to the chosen `Scheduler`. Along Reactor-native operator chains, `Context` survives scheduler hops, whereas `ThreadLocal` and MDC require dedicated propagation bridges. Combining `StepVerifier`, test-owned schedulers, and `WebTestClient` proves **correct metadata, proper execution boundaries, and working Spring WebFlux filter wiring** without relying on `Thread.sleep` or brittle thread names.
