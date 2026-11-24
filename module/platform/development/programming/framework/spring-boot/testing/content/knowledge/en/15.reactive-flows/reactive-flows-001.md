# reactor-test and Testing Publishers Outside the Spring Context

## 1. Goal: Testing Reactive Streams in Plain Java Without Starting Spring

In a Spring Boot application using WebFlux, R2DBC, reactive messaging, or asynchronous services, most logic can be expressed as `Mono<T>` and `Flux<T>`. However, **a Publisher does not need an HTTP server, Spring beans, or an `ApplicationContext` to be tested**. If the unit under test simply accepts data, applies Reactor operators, and returns a `Publisher`, you can instantiate Java objects directly, supply fake dependencies using lambdas or fakes, and verify the **actual signal sequence emitted on subscription** using the `reactor-test` library.

Key focus areas of this lesson:

- Understand `onSubscribe`, `request(n)`, `onNext`, `onComplete`, `onError`, and `cancel()`.
- Use `StepVerifier` for values, ordering, completion, errors, backpressure demand, time, and Reactor `Context`.
- Use `TestPublisher` to actively emit signals from a fake reactive dependency.
- Use `PublisherProbe` to verify **which Publisher branch was actually subscribed to**.
- Write tests that run with JUnit Jupiter **without `@SpringBootTest`, `@WebFluxTest`, `@Autowired`, `@MockBean`, or a server**.
- Distinguish this type of test from `WebTestClient` / Reactive HTTP tests when the requirements involve routes, codecs, filters, or networking.
- Avoid "false green" test pitfalls: assembling without subscribing, calling `subscribe()` in a test and exiting too early, `Thread.sleep`, inappropriate `block()`, emitting to a hot `TestPublisher` at the wrong time, or failing to verify the terminal signal.

**Target stack:** Java 17+, Project Reactor 3.x, JUnit Jupiter; example setup in a Spring Boot 3.x project with Reactor dependencies managed by Boot. Core `reactor-test` APIs also apply to Reactor applications without Spring Boot. For Boot 4.x and newer Reactor release trains, let the project BOM manage versions and check API changes in the corresponding Javadoc.

## 2. Why Are Standard Assertions Not Enough?

### 2.1. A Publisher Is a Pipeline Description, Not a Materialized Value

With Reactor, a call such as:

```java
Mono<String> result = Mono.just("book")
        .map(String::toUpperCase);
```

only creates the pipeline. For a cold publisher like this example, assembling the pipeline **does not prove that processing from source to subscriber was executed**. Signals only flow through the chain once a subscription is triggered.

A common mistake is writing:

```java
@Test
void doesNotVerifyThePublisher() {
    Mono<String> result = Mono.just("book")
            .map(String::toUpperCase);

    assertNotNull(result);
}
```

This is an **anti-pattern** inside a JUnit class with imports. The assertion only proves that an object is non-null. If the transformation returned lowercase, emitted no value, or emitted an error upon subscription, the test would still pass.

A better approach:

```java
StepVerifier.create(Mono.just("book")
        .map(String::toUpperCase))
        .expectNext("BOOK")
        .verifyComplete();
```

The snippet above requires importing `reactor.test.StepVerifier`. It verifies **one value `BOOK`**, followed by **successful completion**, with no extra elements or an error instead of completion.

### 2.2. Types of Reactive Streams Signals

A typical valid sequence:

```text
Subscriber                       Publisher
    |                                |
    | <--------- onSubscribe --------|
    | -------- request(n) ---------->|
    | <--------- onNext(v1) ----------|
    | <--------- onNext(v2) ----------|
    | <--------- onComplete ---------|
    |                                |
    +--- subscription terminated ----+

Or:
    onSubscribe -> request(n) -> onError(exception)

Or:
    onSubscribe -> ... -> cancel()
    (neither onComplete nor onError is required after cancel)
```

Core semantics:

- `onSubscribe` provides a `Subscription`; the subscriber decides how many items it wants to receive via `request(n)`.
- `onNext(value)` delivers a value; a normal `Mono<T>` emits **at most one** `onNext`.
- `onComplete()` ends successfully; a Mono can complete **without emitting any value**.
- `onError(Throwable)` ends with an error. A compliant stream does not emit further `onNext` or terminal signals after a terminal signal has arrived.
- `cancel()` requests to stop receiving further signals; cancellation/cleanup may not occur instantaneously in asynchronous systems.
- `request(n)` is part of the backpressure mechanism, not a "method call count"; sources and operators may adjust demand and prefetch according to their own policies.

**Important:** `Mono.empty()` differs from `Mono.just(null)`. Reactive Streams forbids emitting `null` as an `onNext` value; to represent the absence of data, use `Mono.empty()`. In Reactor, `Mono.just(null)` is not a valid way to emit a "null value".

### 2.3. Subscription Is the Boundary to Verify

A test verifying reactive logic should verify at minimum **the values (if any) and the terminal signal**, or prove that cancellation is intentional. Checking only values without checking the terminal signal can miss a publisher emitting extra items, hanging indefinitely, or emitting an error afterward.

`StepVerifier` is designed to describe expected steps in exact order and **only executes verification when you call a triggering method** such as `verify()`, `verifyComplete()`, or `verifyError()`.

## 3. When Is a Spring Context Not Needed?

A class whose methods return `Mono`/`Flux` can be tested like a plain Java object:

```java
public final class TagFormatter {
    public Flux<String> normalize(List<String> tags) {
        return Flux.fromIterable(tags)
                .map(String::strip)
                .filter(tag -> !tag.isBlank());
    }
}
```

This is an **illustrative class snippet**, assuming Reactor `Flux` and `java.util.List` are imported. If the logic only uses Reactor operators and dependencies can be passed via the constructor, the test **does not need** to start a Boot application.

### 3.1. What Does Skipping the Spring Context Give You?

- No need to run component scanning, auto-configuration, database migrations, or an embedded server.
- Fast tests with minimal shared state, and failures stay focused on Publisher logic.
- Full control to swap data sources with `Mono.just(...)`, `Mono.empty()`, `Mono.error(...)`, `Flux.fromIterable(...)`, `TestPublisher`, or fake implementations.
- Direct control over virtual time/backpressure without forcing an entire Spring application to wait.
- Easy visibility into operator bugs: `map`, `flatMap`, `filter`, `switchIfEmpty`, `timeout`, `retry`, `onErrorResume`, and domain transformations.

### 3.2. What Is Not Proven?

A pure Reactor unit test **does not automatically verify**:

- That Spring `@Bean`, `@Component`, `@ConfigurationProperties`, or Dependency Injection are configured properly.
- WebFlux routes, Controller/RouterFunction, JSON codecs, HTTP validation, or security/web filters.
- That an R2DBC driver actually connects to a DB, transaction manager, broker, or network.
- Reactor Netty HTTP/TCP behavior, socket timeouts, TLS, gateways, and load balancers.

When those items are part of the contract, write appropriate Spring slice/integration tests such as `@WebFluxTest` + `WebTestClient`, `@SpringBootTest`, Testcontainers database tests, or real HTTP integration tests. Do not promote every unit test to `@SpringBootTest` just because a class in the project uses WebFlux.

## 4. Dependencies: `reactor-core` and `reactor-test` Are Two Different Artifacts

### 4.1. Roles

- `io.projectreactor:reactor-core`: contains `Mono`, `Flux`, `Schedulers`, `Context`, and operators used in production.
- `io.projectreactor:reactor-test`: contains `StepVerifier`, `TestPublisher`, `PublisherProbe`, virtual-time support, and test utilities. Used in **test scope** only.
- JUnit Jupiter: test runner/annotations `@Test` and assertions.

**Do not** create a Spring `ApplicationContext` just to get `StepVerifier`. `reactor-test` is a regular Java library that works with Reactive Streams `Publisher` outside Spring.

### 4.2. Gradle Groovy DSL in a Spring Boot 3.x Project

In a `build.gradle` that already has the Spring Boot plugin, dependency management, repositories, and proper Java toolchain:

```groovy
dependencies {
    implementation 'io.projectreactor:reactor-core'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

This is a **dependency/test configuration snippet**, not a complete build file. The Spring Boot BOM manages Reactor versions and related dependencies; do not manually mix Reactor Core and Reactor Test versions from different release trains.

If the project already uses `spring-boot-starter-webflux` in production, `reactor-core` is usually already a transitive dependency, though you should inspect the project's effective dependencies rather than assuming from module names. `reactor-test` should still be clearly declared/resolved in test scope; a compatible test starter might bring it in, but an explicit dependency makes the intent clear.

### 4.3. Maven in a Project with Spring Boot Parent/BOM

```xml
<dependencies>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-core</artifactId>
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
```

Again, this is a **dependency snippet**, not a complete `pom.xml`. The project needs a Java 17+ compiler target/plugin, suitable Surefire/JUnit Platform configuration, and version management.

**Spring Boot 4.x:** starters are split into smaller modules, yet Reactor unit testing tools still use the `reactor-core`/`reactor-test` coordinates. Check the documentation and Dependency BOM of the exact Boot major version instead of mechanically copying Boot 3 web starter configurations. If you are not using Spring Boot, specify the appropriate Reactor version or Reactor BOM yourself.

### 4.4. Verifying Dependency Resolution

```bash
# Gradle Wrapper:
./gradlew dependencyInsight --dependency reactor-core --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency reactor-test --configuration testRuntimeClasspath

# Maven Wrapper:
./mvnw dependency:tree -Dincludes=io.projectreactor
```

Run the matching command for your build tool in the module containing the tests. If it reports that `reactor.test.StepVerifier` cannot be found, verify that `reactor-test` is on `testCompileClasspath`/test scope; having only `reactor-core` is not enough.

## 5. Mastering the `StepVerifier` API Before Practicing

### 5.1. Commonly Used Actions Table

| API | What to Verify |
|---|---|
| `StepVerifier.create(publisher)` | Builds a subscriber scenario for a Publisher |
| `expectSubscription()` | Observes the subscription event |
| `expectNext(value...)` | Next values, in exact order and equality |
| `expectNextMatches(predicate)` | Next value satisfies the predicate |
| `assertNext(consumer)` | Perform custom assertions on a single value |
| `expectNextCount(n)` | Exactly **n** next elements arrive, without checking each value |
| `expectComplete()` | Successful terminal signal after prior steps |
| `expectError(type)` | Error terminal signal of a specific type |
| `expectErrorMatches(predicate)` | Error terminal signal matching a condition, such as type + message |
| `thenRequest(n)` | Sends additional demand upstream |
| `thenCancel()` | Cancels the subscription, suitable for non-terminating Publishers |
| `then(Runnable)` | Executes a staged test action after previous steps, e.g., triggering a `TestPublisher` |
| `thenAwait(duration)` | Waits or advances the virtual clock for data to arrive |
| `expectNoEvent(duration)` | Verifies no events occur during the specified duration |
| `verify()`/`verify(duration)` | **Triggers** the subscription + checks the entire scenario |
| `verifyComplete()` | Shortcut expecting a complete terminal signal and running verify |
| `verifyError(...)` | Shortcut expecting an error terminal signal and running verify |

These methods are not completely interchangeable. For example, `expectNextCount(3)` only asserts **quantity** and will not catch three miscalculated values if ordering/values are not asserted. `expectErrorMessage("...")` checks the message without necessarily constraining the exception type; when the type matters, use `expectErrorMatches`, `expectErrorSatisfies`, or an appropriate assertion.

### 5.2. Examples of Three Basic States

**Publisher with one value and completion:**

```java
StepVerifier.create(Mono.just("DONE"))
        .expectNext("DONE")
        .verifyComplete();
```

**Publisher with no value that completes successfully:**

```java
StepVerifier.create(Mono.<String>empty())
        .verifyComplete();
```

**Publisher emitting an error:**

```java
StepVerifier.create(Mono.<String>error(
        new IllegalStateException("offline")))
        .expectErrorMatches(error ->
                error instanceof IllegalStateException
                && "offline".equals(error.getMessage()))
        .verify();
```

These are **standalone expression snippets**, assuming they are placed inside a test class with Reactor imports. They distinguish *empty completion* from *error*: neither emits `onNext`, yet their terminal signals differ.

### 5.3. Bounding Verification Time

By default, many `verify...` methods have **no timeout**, which can hang if a publisher waits forever. For tests not guaranteed to finish quickly, attach a per-test timeout:

```java
StepVerifier.create(Flux.just(1, 2))
        .expectNext(1, 2)
        .expectComplete()
        .verify(Duration.ofSeconds(3));
```

This example compiles with `java.time.Duration` and Reactor imports. Do not hardcode an extremely low number of seconds for tests involving external resources, nor allow a suite to hang indefinitely. `StepVerifier.setDefaultTimeout(...)` is a **global** setting and can affect tests running in parallel; if used, manage its lifecycle consistently across the test suite.

### 5.4. Do Not Write a Scenario and Forget `verify`

Incorrect pattern:

```java
StepVerifier.create(Mono.just("A"))
        .expectNext("B")
        .expectComplete();
// Missing verify(), verifyComplete(), or verifyError().
```

This is an **anti-pattern**; the test finishes without actually running any Reactive Streams assertions. You must call a terminal verification method. Building a scenario does not mean subscribing.

## 6. Complete Java 17+ Example: Spring-Independent Publisher Logic

We will build a `QuoteService` using `Mono` and `Flux` with **no Spring annotations**, no HTTP, and no database. The product price dependency is represented by a Java interface, and tests can supply fake implementations via lambdas.

### 6.1. File Tree

```text
src/
├── main/java/com/example/reactortesting/
│   └── QuoteService.java
└── test/java/com/example/reactortesting/
    └── QuoteServiceTest.java
```

When run inside a Spring Boot project, these two files are ordinary production and test Java files. `@SpringBootApplication` is unnecessary in this example because we do not boot the app.

### 6.2. Production Source: `QuoteService.java`

**File `src/main/java/com/example/reactortesting/QuoteService.java`:**

```java
package com.example.reactortesting;

import java.time.Duration;
import java.util.List;
import java.util.Locale;
import java.util.NoSuchElementException;
import java.util.Objects;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class QuoteService {

    @FunctionalInterface
    public interface PriceCatalog {
        Mono<Integer> priceFor(String sku);
    }

    public record Quote(String sku, int quantity, int total) {}

    private final PriceCatalog catalog;

    public QuoteService(PriceCatalog catalog) {
        this.catalog = Objects.requireNonNull(catalog);
    }

    public Mono<Quote> quote(String sku, int quantity) {
        return Mono.defer(() -> {
            if (sku == null || sku.isBlank()) {
                return Mono.error(new IllegalArgumentException(
                        "sku required"));
            }
            if (quantity <= 0) {
                return Mono.error(new IllegalArgumentException(
                        "quantity must be positive"));
            }

            return catalog.priceFor(sku)
                    .switchIfEmpty(Mono.error(
                            new NoSuchElementException(
                                    "unknown sku: " + sku)))
                    .map(price -> new Quote(
                            sku,
                            quantity,
                            Math.multiplyExact(price, quantity)));
        });
    }

    public Flux<String> normalize(List<String> tags) {
        return Flux.fromIterable(tags)
                .map(String::strip)
                .filter(tag -> !tag.isEmpty())
                .map(tag -> tag.toUpperCase(Locale.ROOT))
                .distinct();
    }

    public Flux<Long> ticks(Duration period, long count) {
        if (count <= 0) {
            return Flux.error(new IllegalArgumentException(
                    "count must be positive"));
        }
        return Flux.interval(period).take(count);
    }

    public Mono<String> preferred(
            Mono<String> primary,
            Mono<String> fallback) {
        return primary.switchIfEmpty(fallback);
    }

    public Mono<String> traceId() {
        return Mono.deferContextual(context ->
                Mono.just(context.getOrDefault(
                        "traceId", "none")));
    }
}
```

**Notable design points:**

1. `PriceCatalog` is a functional interface, so tests can pass `sku -> Mono.just(1200)` or `sku -> Mono.empty()`. No need to create Mockito mocks or run Spring DI.
2. `quote(...)` uses `Mono.defer(...)` to move validation and the catalog call to **subscription time**. Therefore, merely assembling the pipeline does not read the catalog; tests can verify this distinction.
3. `switchIfEmpty(...)` turns a missing price result into an explicit error. An empty source is not equated with a price of 0.
4. `Math.multiplyExact(int, int)` throws `ArithmeticException` on overflow; Reactor turns exceptions thrown inside operators into terminal errors.
5. `normalize(...)` creates a `Flux<String>` that handles ordering, strips blank strings, normalizes case using `Locale.ROOT`, and removes duplicates, making it useful for testing `onNext` signals.
6. `ticks(...)` creates a time-based stream; tests can use a virtual clock to avoid waiting for hours.
7. `preferred(...)` chooses primary or fallback via `switchIfEmpty`, used to demonstrate `PublisherProbe`.
8. `traceId()` reads the subscriber's **Reactor Context**, not a Spring `ApplicationContext` or `ThreadLocal`.

The example uses no external dependencies, making it suitable for standalone unit tests. In a real application, `PriceCatalog` might be an adapter querying R2DBC/HTTP, though **this unit test intentionally does not verify the real adapter**.

### 6.3. Test Source: `QuoteServiceTest.java`

**File `src/test/java/com/example/reactortesting/QuoteServiceTest.java`:**

```java
package com.example.reactortesting;

import java.time.Duration;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.test.publisher.PublisherProbe;
import reactor.test.publisher.TestPublisher;
import reactor.util.context.Context;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class QuoteServiceTest {

    private QuoteService withCatalog(
            QuoteService.PriceCatalog catalog) {
        return new QuoteService(catalog);
    }

    @Test
    void quoteEmitsExpectedValueAndCompletes() {
        var service = withCatalog(sku -> Mono.just(1200));

        StepVerifier.create(service.quote("BOOK", 2))
                .expectNext(new QuoteService.Quote(
                        "BOOK", 2, 2400))
                .verifyComplete();
    }

    @Test
    void emptyCatalogBecomesDomainError() {
        var service = withCatalog(sku -> Mono.empty());

        StepVerifier.create(service.quote("MISSING", 1))
                .expectErrorSatisfies(error -> {
                    assertEquals(NoSuchElementException.class,
                            error.getClass());
                    assertEquals("unknown sku: MISSING",
                            error.getMessage());
                })
                .verify();
    }

    @Test
    void catalogErrorIsPropagatedAsTerminalError() {
        var service = withCatalog(sku ->
                Mono.error(new IllegalStateException("offline")));

        StepVerifier.create(service.quote("BOOK", 2))
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                        && "offline".equals(error.getMessage()))
                .verify();
    }

    @Test
    void invalidQuantityDoesNotCallCatalog() {
        AtomicInteger calls = new AtomicInteger();
        var service = withCatalog(sku -> {
            calls.incrementAndGet();
            return Mono.just(100);
        });

        StepVerifier.create(service.quote("BOOK", 0))
                .expectErrorMatches(error ->
                        error instanceof IllegalArgumentException
                        && "quantity must be positive"
                                .equals(error.getMessage()))
                .verify();

        assertEquals(0, calls.get());
    }

    @Test
    void catalogIsNotCalledDuringAssembly() {
        AtomicInteger calls = new AtomicInteger();
        var service = withCatalog(sku -> {
            calls.incrementAndGet();
            return Mono.just(500);
        });

        Mono<QuoteService.Quote> pipeline =
                service.quote("PEN", 3);

        assertEquals(0, calls.get());

        StepVerifier.create(pipeline)
                .expectNext(new QuoteService.Quote(
                        "PEN", 3, 1500))
                .verifyComplete();

        assertEquals(1, calls.get());
    }

    @Test
    void fluxNormalizesFiltersAndPreservesFirstOccurrence() {
        var service = withCatalog(sku -> Mono.empty());

        StepVerifier.create(service.normalize(List.of(
                " red ", "RED", "blue", " ", "blue")))
                .expectNext("RED", "BLUE")
                .verifyComplete();
    }

    @Test
    void initialRequestZeroExercisesBackpressure() {
        StepVerifier.create(
                Flux.range(1, 5),
                StepVerifierOptions.create().initialRequest(0))
                .expectSubscription()
                .thenRequest(2)
                .expectNext(1, 2)
                .thenRequest(3)
                .expectNext(3, 4, 5)
                .verifyComplete();
    }

    @Test
    void virtualTimeDoesNotWaitTwoRealHours() {
        var service = withCatalog(sku -> Mono.empty());

        StepVerifier.withVirtualTime(() ->
                service.ticks(Duration.ofHours(1), 2))
                .expectSubscription()
                .expectNoEvent(Duration.ofMinutes(59))
                .thenAwait(Duration.ofMinutes(1))
                .expectNext(0L)
                .thenAwait(Duration.ofHours(1))
                .expectNext(1L)
                .verifyComplete();
    }

    @Test
    void testPublisherControlsTheCatalogSignals() {
        TestPublisher<Integer> source = TestPublisher.create();
        var service = withCatalog(sku -> source.mono());

        StepVerifier.create(service.quote("BOOK", 3))
                .expectSubscription()
                .then(() -> {
                    source.assertWasSubscribed();
                    source.emit(400);
                })
                .expectNext(new QuoteService.Quote(
                        "BOOK", 3, 1200))
                .verifyComplete();
    }

    @Test
    void publisherProbeProvesPrimaryPathWasUsed() {
        var service = withCatalog(sku -> Mono.empty());
        PublisherProbe<String> primary = PublisherProbe.of(
                Mono.just("primary"));
        PublisherProbe<String> fallback = PublisherProbe.of(
                Mono.just("fallback"));

        StepVerifier.create(service.preferred(
                primary.mono(), fallback.mono()))
                .expectNext("primary")
                .verifyComplete();

        primary.assertWasSubscribed();
        primary.assertWasRequested();
        fallback.assertWasNotSubscribed();
    }

    @Test
    void publisherProbeProvesFallbackPathWasUsed() {
        var service = withCatalog(sku -> Mono.empty());
        PublisherProbe<String> primary = PublisherProbe.empty();
        PublisherProbe<String> fallback = PublisherProbe.of(
                Mono.just("fallback"));

        StepVerifier.create(service.preferred(
                primary.mono(), fallback.mono()))
                .expectNext("fallback")
                .verifyComplete();

        primary.assertWasSubscribed();
        fallback.assertWasSubscribed();
        fallback.assertWasRequested();
    }

    @Test
    void reactorContextWorksWithoutSpringApplicationContext() {
        var service = withCatalog(sku -> Mono.empty());

        StepVerifier.create(
                service.traceId(),
                StepVerifierOptions.create().withInitialContext(
                        Context.of("traceId", "trace-42")))
                .expectAccessibleContext()
                .contains("traceId", "trace-42")
                .then()
                .expectNext("trace-42")
                .verifyComplete();
    }

    @Test
    void anInfinitePublisherCanBeCancelled() {
        StepVerifier.create(Flux.never())
                .expectSubscription()
                .thenCancel()
                .verify(Duration.ofSeconds(2));
    }

    @Test
    void aBoundedVerificationCompletesWithinDeadline() {
        StepVerifier.create(Mono.just("READY"))
                .expectNext("READY")
                .expectComplete()
                .verify(Duration.ofSeconds(3));
    }
}
```

This test class has **14 `@Test` methods**. There is no `@SpringBootTest`, `@Autowired`, Spring extension, embedded server, application startup, or intentional stdout. With compatible Java 17+, Reactor Core/Reactor Test, and JUnit Jupiter, **14/14 tests are expected to pass**.

The `StepVerifier.withVirtualTime(...)` test does not actually wait two hours; the virtual scheduler controls simulated time. The other tests use synchronous/deterministic publishers with no `Thread.sleep()`.

### 6.4. Running via Wrapper

**Gradle:**

```bash
./gradlew test --tests "com.example.reactortesting.QuoteServiceTest"
```

**Maven:**

```bash
./mvnw -Dtest=QuoteServiceTest test
```

On Windows PowerShell, use `.\gradlew.bat test --tests "com.example.reactortesting.QuoteServiceTest"` or `.\mvnw.cmd "-Dtest=QuoteServiceTest" test`. The project must have the corresponding wrapper/test task or Maven Surefire/JUnit Platform setup. Do not run both commands if the project only uses one build system.

**Expected result:** the runner reports 14 passing tests; no intentional stdout string is printed by the source. Detailed logs/reports depend on Maven/Gradle/IDE, so verify the actual test count and status rather than copying a console line from another machine.

### 6.5. Detailed Breakdown of Example Scenarios

| Test | Contract Verified | Why It Is Worth Testing |
|---|---|---|
| `quoteEmitsExpectedValueAndCompletes` | Mono emits exactly one `Quote` then completes | Goes beyond checking that the Publisher object is non-null |
| `emptyCatalogBecomesDomainError` | Empty upstream becomes `NoSuchElementException` with exact message | Distinguishes not-found from a source error |
| `catalogErrorIsPropagatedAsTerminalError` | Upstream error is propagated downstream, not swallowed | Verifies exception type/message |
| `invalidQuantityDoesNotCallCatalog` | Invalid input emits error and skips dependency call | Isolates side effects and verifies branching contract |
| `catalogIsNotCalledDuringAssembly` | Dependency is only invoked upon subscription | Proves lazy behavior |
| `fluxNormalizesFiltersAndPreservesFirstOccurrence` | Strips, drops blanks, deduplicates in order | Verifies `onNext` sequence |
| `initialRequestZeroExercisesBackpressure` | Requests 2 then 3 to receive all 5 elements | Tests demand instead of default unbounded |
| `virtualTimeDoesNotWaitTwoRealHours` | Signals emit according to virtual clock | Avoids timing/flaky tests |
| `testPublisherControlsTheCatalogSignals` | Fake emits data after subscription, business pipeline reacts properly | Controls asynchronous source |
| `publisherProbeProvesPrimaryPathWasUsed` | Primary is subscribed/requested, fallback is not subscribed | Verifies actual execution branch |
| `publisherProbeProvesFallbackPathWasUsed` | Empty primary triggers fallback subscription | Verifies `switchIfEmpty` |
| `reactorContextWorksWithoutSpringApplicationContext` | Subscriber Context flows into pipeline | Distinguishes Reactor Context from Spring context |
| `anInfinitePublisherCanBeCancelled` | Non-terminating source can be actively cancelled | Avoids waiting indefinitely for completion |
| `aBoundedVerificationCompletesWithinDeadline` | Verification has a time limit | Prevents suite hangs if source changes to a waiting source |

## 7. Testing `Mono`: onNext, empty, error, and defer

### 7.1. Values Are Not the Entire Contract

A normal `Mono<T>` can:

1. Emit one value and then complete.
2. Complete without emitting any value.
3. Emit an error; it does not complete successfully.
4. Emit no terminal signal within the observation window, e.g., `Mono.never()`.

Tests should clearly distinguish these cases.

**With data:**

```java
StepVerifier.create(Mono.just(42))
        .expectNext(42)
        .verifyComplete();
```

**No data, no error:**

```java
StepVerifier.create(Mono.<Integer>empty())
        .verifyComplete();
```

**Error:**

```java
StepVerifier.create(Mono.<Integer>error(
        new IllegalArgumentException("bad input")))
        .expectError(IllegalArgumentException.class)
        .verify();
```

**Non-terminating source:**

```java
StepVerifier.create(Mono.never())
        .expectSubscription()
        .thenCancel()
        .verify(Duration.ofSeconds(2));
```

These four snippets are **test illustrations**, not four standalone Java programs. For `never` sources, do not use `verifyComplete()` because there is no completion terminal signal to wait for.

### 7.2. `Mono.defer` vs Calling the Source at Assembly Time

Suppose a repository adapter increments a counter every time it is called. If a service invokes the adapter immediately when returning the Publisher:

```java
public Mono<String> eager(String key) {
    Mono<String> remote = repository.find(key);
    return remote.map(String::trim);
}
```

this is an **illustrative snippet** for a class with a suitable `repository` field. The call `repository.find(key)` already happened during **assembly**, even if the I/O inside `remote` only runs upon subscription. Saying "Reactive is always strictly lazy" is an oversimplification.

To defer calling the adapter itself as well:

```java
public Mono<String> lazy(String key) {
    return Mono.defer(() ->
            repository.find(key).map(String::trim));
}
```

In this case, assembling `lazy(key)` does not call `repository.find(key)`; execution is triggered upon subscription. The test in Section 6 explicitly checks this boundary using `AtomicInteger`.

**Caution:** Reactor has both cold and hot publishers. A hot source can produce signals independently of subscriptions; do not mechanically apply "everything starts on subscribe" to every source.

### 7.3. Testing Exceptions Thrown Inside Operators

If `map(...)` throws an exception (such as `Math.multiplyExact` overflowing), Reactor typically converts that exception into an `onError` signal on the pipeline. You can test it with:

```java
StepVerifier.create(
        Mono.just(Integer.MAX_VALUE)
                .map(n -> Math.multiplyExact(n, 2)))
        .expectError(ArithmeticException.class)
        .verify();
```

This is a snippet assuming `Mono`/`StepVerifier` imports. You should not use `assertThrows(() -> Mono.just(...).map(...))` when the exception only occurs **at subscription time**; `assertThrows` around assembly will fail to observe the real error.

### 7.4. Testing `onErrorResume`/`onErrorReturn` Must Check the Terminal Signal

```java
StepVerifier.create(
        Mono.<String>error(
                new IllegalStateException("offline"))
                .onErrorReturn("cached"))
        .expectNext("cached")
        .verifyComplete();
```

When using an error recovery operator, the original source terminates with an error, but the downstream pipeline transforms it into a value and completion. If a test only calls `expectNext("cached")` and omits the terminal check, it can miss a publisher remaining in an abnormal state.

## 8. Testing `Flux`: Ordering, Count, Demand, and Cancellation

### 8.1. Checking Each Element and Order

```java
StepVerifier.create(Flux.just("A", "B", "C"))
        .expectNext("A", "B", "C")
        .verifyComplete();
```

This check is stronger than `expectNextCount(3)` when order and values are part of the contract.

**Choose the right strictness:** with asynchronous `flatMap`, completion order across inner publishers can vary by scheduler. If business logic does not require ordering, do not enforce rigid `expectNext(...)` ordering that creates flaky tests. You can collect into a list and sort intentionally, use `collectList()` with set-equivalent assertions, or switch to an operator like `concatMap` if the contract itself requires ordering.

### 8.2. Backpressure Mechanism: Starting with Demand Zero

By default, `StepVerifier` usually requests **unbounded demand**. If you want to actively test demand, use `initialRequest(0)` or the `StepVerifier.create(publisher, 0)` overload and then send `thenRequest(n)`.

```java
StepVerifier.create(
        Flux.range(1, 4),
        StepVerifierOptions.create().initialRequest(0))
        .expectSubscription()
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(2)
        .expectNext(3, 4)
        .verifyComplete();
```

The snippet above illustrates a synchronous `Flux.range` source that honors demand. It does not prove every source or operator forwards exact 2/2 requests to external systems; many operators use **prefetching, buffering, or demand transformation**.

**Note:** Reactive Streams allows `onComplete`/`onError` in situations independent of whether items have been requested yet. Do not write assertions assuming "before any request, it can never complete or error" as a universal rule.

### 8.3. Testing Cancellation

```java
StepVerifier.create(Flux.never())
        .expectSubscription()
        .thenCancel()
        .verify(Duration.ofSeconds(2));
```

This is an intentional scenario that does not wait for completion. `thenCancel` is an **action on the subscription**; it does not prove that every resource (socket, other subscription, file, executor) has been released immediately. When cleanup is part of the contract, add dedicated tests using mock resources, `doFinally(signalType)`, or appropriate counters.

### 8.4. `expectNextCount` Can Weaken Tests

```java
StepVerifier.create(Flux.just("wrong1", "wrong2"))
        .expectNextCount(2)
        .verifyComplete();
```

This test passes even though the data may be domain-invalid. It only makes sense when **quantity** is what needs verification. Do not replace all `expectNext(value)` calls with `expectNextCount(n)` just to make tests fail less often.

## 9. Testing Time with `StepVerifier.withVirtualTime`

### 9.1. Why Should You Avoid `Thread.sleep()`?

Suppose a service uses `delayElement(Duration.ofHours(2))` or `Flux.interval(Duration.ofHours(1))`. Waiting for real wall-clock time makes the suite painfully slow. Shrinking durations to a few milliseconds makes tests flaky under heavy scheduler/CI load.

`StepVerifier.withVirtualTime(...)` replaces Reactor's default time scheduler with a **virtual scheduler**, allowing the test to advance the clock step by step. This verifies the **relative order of scheduled Reactor signals** without actually waiting for hours.

### 9.2. Must Create the Publisher Inside the `Supplier`

**Correct:**

```java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofHours(1)).take(2))
        .expectSubscription()
        .thenAwait(Duration.ofHours(1))
        .expectNext(0L)
        .thenAwait(Duration.ofHours(1))
        .expectNext(1L)
        .verifyComplete();
```

**Common anti-pattern:**

```java
Flux<Long> alreadyBuilt =
        Flux.interval(Duration.ofHours(1)).take(2);

StepVerifier.withVirtualTime(() -> alreadyBuilt)
        .expectSubscription()
        .thenAwait(Duration.ofHours(2))
        .expectNext(0L, 1L)
        .verifyComplete();
```

In the anti-pattern, the pipeline was already built before the virtual scheduler was activated. Some operators select their scheduler at assembly time; virtual time may fail to intercept the schedule, causing timeouts, hangs, or unpredictable behavior. Therefore, **the `Supplier` must build the pipeline lazily** inside the lambda rather than returning a pre-built object.

### 9.3. `expectNoEvent` Also Counts Subscription as an Event

Correct example:

```java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofHours(1)))
        .expectSubscription()
        .expectNoEvent(Duration.ofMinutes(59))
        .thenAwait(Duration.ofMinutes(1))
        .expectNext(0L)
        .verifyComplete();
```

If you omit `expectSubscription()` and call `expectNoEvent(...)` as the very first step, the test can fail because the subscription event itself occurs during the "no event" window. Place `expectSubscription` before starting the quiet wait.

An event emitted right on a time boundary can make assertions confusing, which is why the example waits **59 minutes with no event** and then advances **the next 1 minute** to reach the emission mark.

### 9.4. Limits of Virtual Time

Virtual time does not fit every case:

- Real APIs, networks, and databases do not run faster just because you advance the Reactor virtual clock.
- Code using `Thread.sleep`, `System.currentTimeMillis`, external clocks, or unreplaced custom schedulers will still depend on real time.
- Operators or schedulers initialized before enabling the virtual clock may not be controlled as expected.
- Infinite streams, complex concurrency, or tasks requiring threads to progress via real mechanisms can stall verification.
- Setting up a virtual scheduler affects Reactor's scheduler factory within the test scope; avoid running conflicting virtual-time tests in parallel when relying on global scheduler state.

The solution is to isolate time-dependent code into small units, pass `Scheduler`/`Clock` when required by design, and use real integration tests for deadlines/timeouts at boundaries outside Reactor.

## 10. `TestPublisher`: A Fake Source Emitting Signals on Demand

### 10.1. How Does It Differ from `Mono.just(...)`?

`Mono.just(400)` is a static source: the value is known upfront. `TestPublisher` lets the test **control when data, errors, or completion are emitted**. This is useful when the code under test needs to handle slow reactive sources, initially empty streams, sequences of values, or errors occurring **after** a subscriber has registered.

Example:

```java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux().map(n -> n * 2))
        .expectSubscription()
        .then(() -> source.next(2, 3).complete())
        .expectNext(4, 6)
        .verifyComplete();
```

The snippet above can be placed in a test method with imports. `then(...)` only executes **after `StepVerifier` has subscribed**, preventing signals from being sent too early.

### 10.2. Hot Source: A Common Mistake Is Emitting Before Subscription

`TestPublisher.create()` normally creates a **hot TestPublisher**. It emits signals to currently registered subscribers and does not necessarily buffer every value to replay to later subscribers.

**Anti-pattern:**

```java
TestPublisher<String> source = TestPublisher.create();
source.next("A");

StepVerifier.create(source.flux())
        .expectNext("A")
        .thenCancel()
        .verify(Duration.ofSeconds(2));
```

The `next("A")` call occurs **before** subscription: with a hot publisher, the test may miss `"A"` and time out or fail. Fix this by emitting inside `then(...)` or using `TestPublisher.createCold()` if the goal is to test replay/cold semantics.

**Note:** `TestPublisher.createCold()` serves cold/replay modeling and is not identical to a hot source. Choose the variant matching the real dependency; do not switch to cold just to patch a test meant to verify hot behavior.

### 10.3. Distinguishing `next`, `complete`, `error`, and `emit`

- `next(value)` sends `onNext`.
- `complete()` sends `onComplete`.
- `error(exception)` sends `onError`.
- `emit(values...)` sends one or more values and then completes.

Error test example:

```java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux())
        .expectSubscription()
        .then(() -> source.error(
                new IllegalStateException("downstream failed")))
        .expectErrorMatches(error ->
                error instanceof IllegalStateException
                && "downstream failed".equals(error.getMessage()))
        .verify();
```

**Do not mix** an `onComplete` followed by another `onNext` on a compliant publisher. If you intentionally need to test how code handles spec-violating sources, Reactor provides `TestPublisher.createNoncompliant(...)` with specific `Violation` flags; that is a dedicated resilience test, not a default source for business unit tests.

### 10.4. `TestPublisher` and Checking Requests/Subscribers

Depending on the version, `TestPublisher` supports assertions such as `assertSubscribers(...)`, `assertMinRequested(...)`, `assertMaxRequested(...)`, and `assertCancelled(...)`. These assertions apply at specific points in time; some `TestPublisher` setups clear subscribers upon termination, causing assertions **after completion** not to reflect the prior subscription the way you might expect.

In the runnable example, `source.assertWasSubscribed()` is placed **inside `then(...)` and before `emit(...)`**, ensuring a clear observation point. If the goal is to verify branch subscription **after the source has finished**, prefer `PublisherProbe` instead of overusing `TestPublisher` internal state.

### 10.5. Do Not Use Intentionally Noncompliant Test Sources as a General Baseline

A publisher emitting `null`, emitting `onNext` past demand, emitting signals after completion, or sending multiple terminal signals represents a broken upstream. `createNoncompliant(...)` helps reproduce these to test operator/adapter robustness, but **such signals must not be treated as valid Reactive Streams behavior**. Distinguish clearly between "testing that an ill-behaved upstream doesn't hang the pipeline" and "simulating standard upstream behavior".

## 11. `PublisherProbe`: Verifying Whether a Fallback Branch Was Subscribed To

### 11.1. Why Asserting Values Alone May Not Be Enough

Suppose:

```java
Mono<String> selected =
        primary.switchIfEmpty(fallback);
```

When `primary` emits a value, `fallback` should not be subscribed to. However, if both sources happen to return the string `"OK"`, simply calling `expectNext("OK")` does not prove **which branch executed**.

`PublisherProbe` wraps a Publisher to record subscribe/request/cancel events without requiring the test to emit data manually via `TestPublisher`.

### 11.2. Primary Has a Value: Fallback Must Not Be Subscribed To

```java
PublisherProbe<String> primary = PublisherProbe.of(
        Mono.just("FIRST"));
PublisherProbe<String> fallback = PublisherProbe.of(
        Mono.just("BACKUP"));

StepVerifier.create(
        primary.mono().switchIfEmpty(fallback.mono()))
        .expectNext("FIRST")
        .verifyComplete();

primary.assertWasSubscribed();
primary.assertWasRequested();
fallback.assertWasNotSubscribed();
```

This is a snippet with corresponding imports. It carries stronger guarantees than just matching `"FIRST"`: the test catches bugs where code accidentally subscribes to `fallback`, even if the final value happens to match expectations.

### 11.3. Primary Is Empty: Fallback Is Subscribed To

```java
PublisherProbe<String> primary = PublisherProbe.empty();
PublisherProbe<String> fallback = PublisherProbe.of(
        Mono.just("BACKUP"));

StepVerifier.create(
        primary.mono().switchIfEmpty(fallback.mono()))
        .expectNext("BACKUP")
        .verifyComplete();

primary.assertWasSubscribed();
fallback.assertWasSubscribed();
fallback.assertWasRequested();
```

Use `PublisherProbe.empty()` to create a source that completes empty while still recording subscribe/request behavior. This is the classic test case for `switchIfEmpty`.

### 11.4. `TestPublisher` and `PublisherProbe` Answer Two Different Questions

| Tool | What Do You Actively Control? | What Do You Measure? |
|---|---|---|
| `Mono.just/empty/error` | Simple static data, completion/error | Pipeline outcome via `StepVerifier` |
| `TestPublisher` | Timing/source signals `onNext/onError/onComplete` | Behavior when downstream receives controlled signals |
| `PublisherProbe` | Wraps an existing Publisher or empty source | Whether the branch was subscribed/requested/cancelled |
| `StepVerifier` | Subscriber scenario, demand/time/cancel | Downstream signals and termination of the chain under test |

`TestPublisher` and `PublisherProbe` can be combined in a single test, though neither is needed if `Mono.just(...)` and `StepVerifier` already suffice to prove the contract.

## 12. Testing Reactor `Context` Without a Spring `ApplicationContext`

### 12.1. Two Completely Different Context Concepts

- **Spring `ApplicationContext`:** container holding beans, managing dependency injection, lifecycle, and configuration.
- **Reactor `Context`:** data attached to a subscription so operators can read it via APIs like `Mono.deferContextual(...)` and `contextWrite(...)`; it is neither a Spring bean registry nor a `ThreadLocal`.

With `reactor-test`, you can attach an initial context to `StepVerifier`:

```java
StepVerifier.create(
        Mono.deferContextual(context ->
                Mono.just(context.get("traceId"))),
        StepVerifierOptions.create().withInitialContext(
                Context.of("traceId", "trace-A")))
        .expectNext("trace-A")
        .verifyComplete();
```

This is an illustrative snippet in a Java test with imports. The value `trace-A` comes from the **Reactor subscriber context**, not Spring DI.

### 12.2. `expectAccessibleContext` Is an Advanced Check

In the complete test suite, we use:

```java
StepVerifier.create(
        service.traceId(),
        StepVerifierOptions.create().withInitialContext(
                Context.of("traceId", "trace-42")))
        .expectAccessibleContext()
        .contains("traceId", "trace-42")
        .then()
        .expectNext("trace-42")
        .verifyComplete();
```

`expectAccessibleContext()` verifies that the pipeline has an accessible context; `contains(...)` asserts the key/value; `then()` returns to signal expectations. Some publishers that do not adhere to Reactor's context-propagation mechanics might not expose context this way; test the exact operators and libraries you use.

**Do not assume** Reactor Context automatically propagates MDC/`ThreadLocal` or Spring Security context across every thread. Context propagation integration is a separate topic depending on operators, schedulers, and framework support.

## 13. Time, Schedulers, and Real Asynchronous Tests

### 13.1. Why Are Tests Using `Thread.sleep` Flaky?

An anti-pattern:

```java
AtomicReference<String> seen = new AtomicReference<>();

service.someAsyncMono().subscribe(seen::set);
Thread.sleep(50);
assertEquals("OK", seen.get());
```

This is an **anti-pattern snippet**, assuming methods/fields exist. Under heavy CI load or scheduler delays, the subscriber might not receive the value within 50 ms even when the code is right. If the source emits an error without a handler, the test can lose information or log elsewhere; a bare async `subscribe()` **does not make JUnit wait for completion**.

Replace with `StepVerifier`:

```java
StepVerifier.create(service.someAsyncMono())
        .expectNext("OK")
        .expectComplete()
        .verify(Duration.ofSeconds(3));
```

This snippet assumes a real service and matching method signature; it forces the test to wait within a bound, verifying both value and terminal signal. Do not use `block()` merely to turn every Reactive test into an imperative test when you need to verify multiple signals, backpressure, cancellation, or `Context`.

### 13.2. When Is `block()` Still Acceptable?

`block()` can be useful at the boundary between reactive and imperative code in certain test utilities or CLIs, but it:

- Only retrieves the terminal/value result according to its semantics and does not assert the order of multiple `onNext` signals.
- Can blur the distinction between empty completion and certain `null` handling cases.
- Does not directly verify backpressure and request signals.
- Can fail if invoked on a Reactor non-blocking event-loop thread.

For pipeline tests, `StepVerifier` generally expresses the contract better. If you only evaluate a simple `Mono`, still test error/empty cases and set intentional timeouts.

### 13.3. Injected Schedulers vs Global Virtual Schedulers

If a service accepts a `Scheduler` via its constructor, you can pass a `VirtualTimeScheduler` or a dedicated test scheduler for that unit instead of relying entirely on replacing the default Scheduler factory. This option helps when code uses `publishOn(scheduler)` / `subscribeOn(scheduler)` with a non-default scheduler.

Even when injecting a scheduler directly, you must still manage its lifecycle, disposal, and test isolation. `VirtualTimeScheduler` does not replace every Java clock or I/O system.

### 13.4. `publishOn`, `subscribeOn`, and Signal Ordering

These operators can change execution threads and affect scheduling. `StepVerifier` still checks the order of **signals seen by the subscriber**. However, do not assert specific thread names unless that is a promise explicitly made by the API contract.

When code uses `flatMap` with concurrency, inner source completion order can vary. To verify order, use an ordering-preserving operator or order-independent assertions when business rules do not require order. Relying on real wall-clock timing to produce an accidental order usually leads to flaky tests.

## 14. Test Correctness: Signals, Errors, Cancellation, and Side Effects

### 14.1. Asserting Only Values Misses Resource Cleanup

A pipeline might emit `"OK"` properly yet leak resources on cancellation. When cleanup is part of the contract, verify the specific side effect via `doFinally(...)` or a fake resource/counter:

```java
AtomicInteger finallyCalls = new AtomicInteger();

Flux<Integer> source = Flux.<Integer>never()
        .doFinally(signalType ->
                finallyCalls.incrementAndGet());

StepVerifier.create(source)
        .expectSubscription()
        .thenCancel()
        .verify(Duration.ofSeconds(2));

assertEquals(1, finallyCalls.get());
```

This snippet is tailored for synchronous `Flux.never()` and `doFinally`, using `AtomicInteger`. For cleanup tasks that run asynchronously, do not assert that the counter updated immediately on the test thread; wait/observe appropriately and manage real resources properly.

### 14.2. If Upstream Errors, There Is No Successful `onComplete`

A valid reactive pipeline cannot emit a terminal `onError` and also continue with `onComplete` as a second terminal signal. With `onErrorResume`, an upstream terminal error is **transformed** into another Publisher, allowing downstream to finish successfully. Distinguish "upstream errored" from "the publisher the test subscribed to emitted an error".

Example:

```java
StepVerifier.create(
        Mono.<String>error(new IllegalStateException("fail"))
                .onErrorResume(error -> Mono.just("recovered")))
        .expectNext("recovered")
        .verifyComplete();
```

### 14.3. Error Messages and Object Identity

Tests should assert the exception type and relevant message parts when they belong to the contract. Avoid coupling tests to full stack traces or messages containing object addresses or implementation-specific timing details.

For domain errors, `expectErrorSatisfies(...)` can leverage JUnit/AssertJ assertions:

```java
StepVerifier.create(
        Mono.<String>error(
                new IllegalArgumentException("bad quantity")))
        .expectErrorSatisfies(error -> {
            assertEquals(IllegalArgumentException.class,
                    error.getClass());
            assertEquals("bad quantity", error.getMessage());
        })
        .verify();
```

Across JVMs and test suites, stack trace details may vary, while the exception type and message you check remain stable.

## 15. When Should You Add Spring Tests or `WebTestClient`?

This lesson deliberately stays **outside the Spring context**. Yet a reactive service layer interacts with many boundaries; choose the right test type:

| Goal | Usually Suitable Tool |
|---|---|
| Pure `Flux/Mono` functions, filter/map/retry/timeout | JUnit + `reactor-test`, no Spring |
| Service using an adapter interface returning Mono/Flux | Fake/`TestPublisher`/`PublisherProbe` + `StepVerifier` |
| Validate DI, configuration properties, conditional beans | Appropriate Spring test context |
| WebFlux controller/router HTTP contract | `@WebFluxTest` or `WebTestClient` |
| Real R2DBC repository queries | R2DBC integration tests with a test database |
| `WebClient` request/response protocol | Mock web server / contract test, or version-appropriate `WebClient` test utilities |
| TCP/HTTP server/network behavior | `RANDOM_PORT` + HTTP client or environment-level tests |
| Security filter chain / authorization | Corresponding Spring Security test integration |
| Correctness of custom Reactive Streams subscriber/operator | `StepVerifier`/`TestPublisher`, plus spec compliance tests if needed |

**Do not interpret "without a Spring context" as "you cannot test publishers built in a Spring Boot app".** Simply isolate the logic unit and pass the needed dependencies. Whether beans are actually registered and wired by Boot configuration is a separate contract tested at a higher layer.

### 15.1. Should You Use `@WebFluxTest` to Test a `map` Operator?

Usually not. `@WebFluxTest` boots the web slice, which is heavier than plain JUnit. If you only need to verify `Flux.range(1,5).map(n -> n*2)`, a few lines of `StepVerifier` are plenty. Use WebFlux tests when you actually need route mappings, codecs, validation, controller advice, or web filters.

### 15.2. Can `WebTestClient` Run Without Starting a Server?

Yes, when bound to a controller or application context, `WebTestClient` can test handlers and the reactive web stack **without opening an HTTP socket**. Still, that is a **web-level testing** tool, distinct from subscribing directly to `Mono`/`Flux` via `StepVerifier`. The name `WebTestClient` alone does not tell whether requests traverse a real network; check whether the setup binds to a controller/context or to a live server.

## 16. Debugging and Diagnosing `StepVerifier` Failures

### 16.1. When a Test Expects `onNext` but Receives `onError`

- Check whether the data source emitted `Mono.error` or an operator threw an exception.
- Check whether the error occurred before or after `switchIfEmpty`/`onErrorResume`.
- Confirm you subscribed to the Publisher after all operators were applied.
- Check mappers for nulls, arithmetic overflow, or `IllegalArgumentException`.
- Do not loosen expectations to accept any error if the domain contract requires a value.

For example, with `quote(...)`: if the catalog returns `Mono.empty()`, the service contract specifies an `unknown sku` error, not a default `Quote`. A proper test should expect that error.

### 16.2. When a Test Times Out or Hangs Indefinitely

- Did you call a `verify...` method?
- Does the Publisher have a terminal signal, or is it `Flux.never()`?
- Did `StepVerifier` start with initial request 0 and forget `thenRequest(n)`?
- When using virtual time, was the Publisher created inside the `Supplier`?
- Is there a `Thread.sleep` or a custom scheduler not virtualized?
- Did a hot `TestPublisher` emit signals **before** subscription?
- Is a pipeline blocking its own event-loop via `block()` or synchronization?
- Is async code holding a resource or deadlocked on a lock?

Setting `verify(Duration)` is a helpful safeguard, though a timeout only reports that **the scenario was not observed within the deadline**; it does not diagnose the root cause on its own.

### 16.3. When a Test "Passes" Without Running Logic

- Did it only call `assertNotNull(mono)`?
- Did it create `StepVerifier.create(...).expectNext(...)` and forget `verify`?
- Did it call `subscribe()` directly and let the JUnit method exit before results/errors arrived?
- Did it stub too deeply, replacing the logic under test with `Mono.just(...)`?
- Is an assertion like `expectNextCount(n)` too weak?
- Was `PublisherProbe` placed in the wrong spot, measuring a Publisher already subscribed elsewhere?
- Did it compare Publisher objects instead of the signals they emit?

A reliable test checks **downstream behavior** at the right boundary and, when needed, **which upstream branch was used**.

### 16.4. When `reactor-test` Classes Are Missing

Common imports:

```java
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.test.publisher.TestPublisher;
import reactor.test.publisher.PublisherProbe;
```

If the build fails with "package reactor.test does not exist", check that the `reactor-test` dependency is in test scope, under proper dependency management, and in the test source set. Do not add `@SpringBootTest` just to fix a missing import. When Reactor versions are mixed, align to the compatible BOM/managed dependencies.

### 16.5. When Context Assertions Fail

Reactor `Context` is subscriber-scoped data, not a global variable. If code reads context from another location, attaches initial context without propagating through a Reactor-aware Publisher, or uses a non-Reactor publisher, expectations may fail. Check `deferContextual` and the upstream direction of `contextWrite`; do not assume data automatically becomes `ThreadLocal`.

## 17. Common Misconceptions

**"You must use `@SpringBootTest` to test a `Mono`."** False. Reactor is an independent library; JUnit + `reactor-test` can test Publishers directly.

**"Creating a Mono means the code already ran."** Not for most cold/lazy sources. Assembly, subscription, and signal emission are distinct phases.

**"`StepVerifier.create(...)` automatically runs all assertions."** False. You must invoke a verify method.

**"`Mono.empty()` and `Mono.error(...)` both return no value, so they are the same."** False. One is a successful completion, the other a terminal error.

**"`expectNextCount(5)` is enough to prove 5 values are correct."** False. It only verifies the count of `onNext` signals.

**"You can use `Thread.sleep(20)` to be sure an async publisher finishes."** Unreliable, especially in CI.

**"Virtual time makes all network I/O finish instantaneously."** False. It controls compatible Reactor time schedulers, not external servers.

**"`expectNoEvent` can go first before `expectSubscription`."** Error-prone because subscription itself counts as an event.

**"`TestPublisher.create()` always replays every signal."** False. Hot publishers do not guarantee replay of `onNext` signals sent prior to subscription.

**"`PublisherProbe` requires manually emitting data like `TestPublisher`."** False. It wraps a Publisher or empty source and observes subscribe/request/cancel events.

**"Calling `block()` is how you test backpressure."** False. `block()` cannot drive `request(n)` and signal-by-signal scenarios like `StepVerifier`.

**"Reactor Context is the same as Spring ApplicationContext."** False. Their scopes, purposes, and mechanisms are completely different.

## 18. Practice Exercises and Solutions

### Exercise A. A Successful Mono with No Value

Test `Mono.empty()` without using `block()`.

**Solution:**

```java
StepVerifier.create(Mono.<String>empty())
        .verifyComplete();
```

Do not use `expectNext(null)` because Reactor does not treat `null` as a valid `onNext` value.

### Exercise B. A Source Emitting Two Elements Followed by an Error

Create `Flux.just("A", "B").concatWith(Mono.error(new IllegalStateException("stop")))`. Verify A, B in order, followed by an `IllegalStateException` error.

**Solution:**

```java
StepVerifier.create(
        Flux.just("A", "B")
                .concatWith(Mono.error(
                        new IllegalStateException("stop"))))
        .expectNext("A", "B")
        .expectError(IllegalStateException.class)
        .verify();
```

This is a JUnit test snippet with imports. Note that `concatWith` produces a Flux ending in error, so do **not** use `verifyComplete()` here.

### Exercise C. Actively Emit an Error After Subscription

Use `TestPublisher` to simulate an upstream reporting offline after subscription.

**Solution:**

```java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.mono())
        .expectSubscription()
        .then(() -> source.error(
                new IllegalStateException("offline")))
        .expectErrorMessage("offline")
        .verify();
```

The crucial detail is emitting `error` inside `then(...)`, after subscription. If you only assert the message, the exception type is not verified; use `expectErrorMatches` when the domain contract requires both type and message.

### Exercise D. Why Does a `Flux.interval` Test Hang?

You created `Flux.interval(Duration.ofDays(1))` **before** calling `StepVerifier.withVirtualTime(() -> existingFlux)`. Fix it.

**Solution:** put the `Flux.interval(...)` call **inside the supplier**, call `expectSubscription()`, then `thenAwait(Duration.ofDays(1))` and `expectNext(0L)`. If the source is infinite, call `thenCancel()` after the verified portion instead of waiting for `verifyComplete()`.

### Exercise E. Primary and Fallback Have the Same Value

Given both primary and fallback returning `Mono.just("OK")`, how do you prove fallback was not subscribed to?

**Solution:** wrap both sources with `PublisherProbe.of(...)`, subscribe to `primary.mono().switchIfEmpty(fallback.mono())`, have `StepVerifier` expect `"OK"` then `verifyComplete()`, and then assert `primary.assertWasSubscribed()` and `fallback.assertWasNotSubscribed()`. Checking only `"OK"` cannot distinguish the branches.

### Exercise F. Verify Exact Demand on `Flux.range`

Source is `Flux.range(1, 4)`, initial request 0. Request 1 then request 3, expecting 1, then 2/3/4, then complete.

**Solution:**

```java
StepVerifier.create(Flux.range(1, 4), 0)
        .expectSubscription()
        .thenRequest(1)
        .expectNext(1)
        .thenRequest(3)
        .expectNext(2, 3, 4)
        .verifyComplete();
```

When testing more complex publishers, keep in mind that operators may prefetch or batch demand; this exercise uses `Flux.range` so the behavior is straightforward to verify.

### Exercise G. Required Level of Testing

A service returns `Mono<Order>` and depends on a repository interface; you want to test the fallback when the repository returns empty. Do you need a real R2DBC database or Spring context?

**Solution:** if the goal is **fallback logic**, no. Use a fake `repository.findById(...) -> Mono.empty()` and `StepVerifier`. If you want to prove the repository's SQL queries and transactions work against a database, write a separate integration test with an appropriate DB/test fixture.

## 19. Quality Checklist Before Finalizing a Reactive Test

- [ ] Identified whether the publisher under test is `Mono` or `Flux`, cold or hot, finite or infinite.
- [ ] Described value signals, terminal signal, and cancel/demand effects if part of the contract.
- [ ] Included a final method triggering verification: `verify()`, `verifyComplete()`, or equivalent.
- [ ] Did not use `assertNotNull(publisher)` in place of value/terminal checks.
- [ ] Did not use `Thread.sleep` to wait for asynchronous logic in CI.
- [ ] Did not call `subscribe()` and let the test exit before results/errors arrive.
- [ ] For errors, asserted the proper type/message or predicate per the contract.
- [ ] For empty streams, verified successful completion, never expecting a `null` value.
- [ ] For a Flux with business ordering, asserted the exact sequence of elements.
- [ ] For backpressure, configured initial request and `thenRequest` deliberately.
- [ ] For infinite sources, used `thenCancel` instead of waiting for completion.
- [ ] For virtual time, built the Publisher inside the `Supplier` after the scheduler was enabled.
- [ ] Called `expectSubscription` before `expectNoEvent`.
- [ ] Did not expect virtual time to speed up network/DB/`Thread.sleep`.
- [ ] For hot `TestPublisher`, emitted signals after subscription via `then(...)`.
- [ ] Did not use a noncompliant publisher as the default business source model.
- [ ] With `PublisherProbe`, asserted subscribe/request branches explicitly.
- [ ] Did not confuse Reactor Context with Spring ApplicationContext or `ThreadLocal`.
- [ ] Aligned `reactor-core`/`reactor-test` versions with the Boot BOM.
- [ ] Avoided starting a Spring context when only testing Reactive Streams logic.
- [ ] Added separate integration tests for DI, WebFlux endpoints, codecs, security, R2DBC, or networking when needed.
- [ ] Used reasonable timeouts for tests at risk of hanging indefinitely.
- [ ] Ran the right test task and checked the executed test count in IDE/Gradle/Maven/CI.

## 20. Conclusion

**`reactor-test` is the tool for verifying Reactive Streams contracts directly on Publishers, independent of the Spring context.** `StepVerifier` describes and checks each signal upon subscription; `TestPublisher` lets you drive upstream signals; `PublisherProbe` confirms which Publisher branch was used; and virtual time and demand allow testing timing and backpressure clearly and quickly.

A good Reactive unit test does not need to boot the entire application: it needs **valid data sources or fakes**, **assertions on values and terminal signals**, and **control over time, subscription, demand, or cancellation when part of the contract**. Leave `@WebFluxTest`, `@SpringBootTest`, and real HTTP/DB tests to verify the framework and infrastructure boundaries that publisher unit tests cannot prove on their own.

## Official References

- [Project Reactor — Testing (Reference Guide)](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, time manipulation, `TestPublisher`, `PublisherProbe`, and Reactor Context.
- [Project Reactor — StepVerifier Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): expectations, verify, initial request, cancellation, and timeouts.
- [Project Reactor — StepVerifierOptions Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifierOptions.html): `initialRequest`, `scenarioName`, and `withInitialContext`.
- [Project Reactor — TestPublisher Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html): hot/cold Publisher, signals, noncompliant modes, and assertion timing.
- [Project Reactor — PublisherProbe Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html): verifying subscribe/request/cancel on a branch.
- [Project Reactor — Mono & Flux](https://projectreactor.io/docs/core/release/reference/coreFeatures.html): fundamentals of reactive pipelines.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): distinguishing unit testing from Spring application/web tests.
- [Reactive Streams JVM Specification](https://github.com/reactive-streams/reactive-streams-jvm): rules for request, onNext, onError, onComplete, and cancellation.
