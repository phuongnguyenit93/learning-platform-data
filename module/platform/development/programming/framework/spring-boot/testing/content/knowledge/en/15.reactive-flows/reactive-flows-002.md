# Reactive Flows — StepVerifier: Values, Completion, and Error Signals

## Objectives

When working with Spring WebFlux, a service typically does not directly return an `Order`, a `List<Order>`, or throw an exception at the moment the method is invoked. Instead, it returns **`Mono<T>` or `Flux<T>`** — a `Publisher` describing the signals to be sent when a subscriber attaches. Proper testing must verify **the signals and their order**, rather than just inspecting the created publisher object.

`StepVerifier` belongs to Project Reactor's **`reactor-test`** library. It lets you write a scenario: subscribe → expect specific `onNext` signals → receive `onComplete` **or** `onError` → execute `verify`. It is the central tool for testing reactive logic in Java/Spring Boot.

After this lesson, you will be able to:

- Distinguish `onSubscribe`, `onNext`, `onComplete`, `onError`, and cancellation.
- Verify **emitted values**, count, order, predicates on data, and absence of emitted values.
- Test `Mono.empty()`, `Flux.empty()`, and the difference between **normal emptiness** and **error**.
- Use `expectError`, `expectErrorMatches`, `expectErrorSatisfies`, and `verifyError` to protect error contracts.
- Understand that `verifyComplete()` does not mean "received a value"; it also requires the stream to **end successfully** with no extra signals.
- Test streams under **backpressure** using `initialRequest` and `thenRequest`.
- Test delays/timeouts without waiting for wall-clock time using `withVirtualTime`.
- Distinguish `StepVerifier` unit tests from HTTP testing with `WebTestClient`.
- Run a complete example with **Java 17, Spring Boot 3.3.x, Reactor Core, reactor-test, Gradle, and JUnit Jupiter**.

**Key idea:** A Reactor test must assert the **final outcome of the signal sequence**: a publisher emits the right data and completes, or emits some data and errors, or completes immediately without emitting data. Omitting the terminal signal check can leave the desired contract unprotected.

## 1. The Reactive Streams Signal Model

For a normal subscription, Reactive Streams looks like this:

~~~text
Subscriber                      Publisher
    |                               |
    |---- subscribe() ------------->|
    |<--- onSubscribe(subscription)-|
    |---- request(n) -------------->|
    |<--- onNext(value_1) ----------|
    |<--- onNext(value_2) ----------|
    |<--- ... ----------------------|
    |<--- onComplete() -------------|  success

or

    |<--- onError(exception) -------|  failure
~~~

Rules to remember:

1. **`onSubscribe`** establishes a subscription.
2. **`onNext(T)`** carries a value. `Flux` may emit 0, 1, or many values; `Mono` normally emits **at most one** value.
3. **`onComplete()`** finishes successfully, even if **no values** were emitted beforehand.
4. **`onError(Throwable)`** finishes with an error. It is **never followed by `onComplete`** on the same subscription.
5. After a terminal signal (`onComplete`/`onError`), a compliant publisher must not continue emitting `onNext`.
6. A subscriber can **cancel** before receiving a terminal signal; cancelling is not the same as "the stream completed on its own".
7. The number of `onNext` signals is bounded by demand (`request(n)`) for backpressure-respecting publishers.

Signal examples from familiar publishers:

| Publisher | Observed Signals |
| --- | --- |
| `Mono.just("A")` | `onNext("A")` → `onComplete` |
| `Mono.empty()` | `onComplete` (no `onNext`) |
| `Mono.error(new IllegalArgumentException("bad"))` | `onError(IllegalArgumentException)` |
| `Flux.just("A", "B")` | `onNext("A")` → `onNext("B")` → `onComplete` |
| `Flux.concat(Flux.just("A"), Flux.error(...))` | `onNext("A")` → `onError` |
| `Flux.never()` | No `onNext`, no terminal signal until cancelled or stopped externally |

Because `onComplete` and `onError` are **mutually exclusive**, a test expecting an error must not also expect completion. For non-terminating streams, a test calling `verifyComplete()` without a timeout can wait indefinitely. Depending on your goal, use cancellation, a finite timeout, or virtual time.

### A Publisher Has Not Necessarily Run When Its Method Returns

~~~java
Mono<String> greeting = Mono.fromSupplier(() -> {
    System.out.println("supplier executed");
    return "hello";
});
~~~

This snippet only constructs the `Mono` without executing the supplier. The supplier usually executes **upon subscription**. `StepVerifier.create(greeting)` builds the scenario, while one of `verifyComplete()`, `verifyError(...)`, or `verify()` triggers the subscription and signal verification.

Never use `assertNotNull(greeting)` to conclude that reactive logic works. That assertion only checks that the Java `Mono` object exists.

## 2. Correct Dependencies and Imports

**Gradle** in a Spring Boot module using WebFlux:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
~~~

This is a dependency block to add to a `build.gradle` already configured with the Spring Boot plugin and compatible dependency management. The full runnable project is in Section 7.

**Important imports**:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import org.junit.jupiter.api.Test;
~~~

`StepVerifier` resides in package `reactor.test`, not `reactor.core.publisher` and not JUnit by default. If your IDE reports `reactor.test.StepVerifier` cannot be found, verify that `io.projectreactor:reactor-test` is on the **test classpath** and not excluded.

When testing pure Reactor code, there is no need to run `@SpringBootTest`. A unit test can instantiate the service with `new` and use `StepVerifier` to test `Mono`/`Flux` right away. `@SpringBootTest` is only needed when the test aims to prove **Spring bean wiring, auto-configuration, or cross-layer application interactions**.

## 3. Structure of a `StepVerifier` Scenario

Basic scenario:

~~~java
StepVerifier.create(Flux.just("BOOK", "PEN"))
        .expectNext("BOOK")
        .expectNext("PEN")
        .expectComplete()
        .verify();
~~~

This is a snippet suitable for a `@Test` method with imports. Each step has a role:

| Part | Meaning |
| --- | --- |
| `StepVerifier.create(publisher)` | Prepares to subscribe to the Publisher on verify |
| `expectSubscription()` | Requires observing the subscribe signal |
| `expectNext(value)` | Requires the exact next `onNext` value |
| `expectNextCount(n)` | Requires `n` values next without checking each value's content |
| `expectNextMatches(predicate)` | Checks the next value using a predicate |
| `assertNext(consumer)` | Runs custom assertions on the next value |
| `expectComplete()` | Requires the `onComplete` terminal signal |
| `expectError(...)` | Requires a matching `onError` terminal signal |
| `thenCancel()` | Cancels the subscription after reaching the desired step |
| `verify()` | **Actually subscribes and executes** the verification scenario |
| `verifyComplete()` | Shorthand for expecting completion + verify |
| `verifyError(...)` | Shorthand for expecting error + verify |

In the example above, the two `expectNext` calls check both **content and order**, while `expectComplete` ensures no more items follow `PEN` and the publisher finishes normally. `verify()` is the triggering step.

### Shorthand Form

The following two scenarios are equivalent:

~~~java
StepVerifier.create(Flux.just(1, 2))
        .expectNext(1, 2)
        .expectComplete()
        .verify();
~~~

~~~java
StepVerifier.create(Flux.just(1, 2))
        .expectNext(1, 2)
        .verifyComplete();
~~~

In modern code, `verifyComplete()` reads naturally: "after the expected values, the stream must complete". However, do not use it for streams **designed to emit an error**.

### Completely Empty Case

~~~java
StepVerifier.create(Mono.empty())
        .verifyComplete();
~~~

This test passes **even with zero `onNext` signals**. If the requirement states "must find an invoice", do not write only `verifyComplete()`; include `expectNext(...)` or an assertion so an accidentally empty publisher is caught.

If you use `Mono.justOrEmpty(null)`, the result is also an empty completion. Reactive Streams **does not allow emitting `null` as an `onNext` value**; to represent "no data", use empty or a dedicated data structure describing status.

## 4. Verifying Values: Exact Match, Predicate, Custom Assertion, and Count

### `expectNext` for Exact Value Contracts

~~~java
StepVerifier.create(Flux.just("A", "B", "C"))
        .expectNext("A", "B", "C")
        .verifyComplete();
~~~

There are three requirements here: exactly **3 values**, **in the right order**, and **successful completion right after**. If the publisher emits `A`, `C`, `B` or emits an extra `D`, the test fails.

With Java records that implement component-wise `equals`, `expectNext(new Quote(...))` works cleanly. For mutable objects or objects without `equals`, verifying via predicate or `assertNext` expresses the contract more clearly.

### `expectNextMatches` for Predicate Checks

~~~java
StepVerifier.create(Mono.just("INV-2026-001"))
        .expectNextMatches(id ->
                id.startsWith("INV-")
                        && id.length() > 5)
        .verifyComplete();
~~~

The predicate returns `true` when the value meets the requirement. Advantage: no need to hardcode entire dynamic IDs. Limitation: an overly weak predicate (e.g., just `id != null`) lets invalid behavior slip through; if the contract requires an exact ID, use `expectNext(expectedId)`.

### `assertNext` for Checking Multiple Object Fields

~~~java
StepVerifier.create(Mono.just(
        new Quote("BOOK", 24000L)))
        .assertNext(quote -> {
            assertEquals("BOOK", quote.sku());
            assertEquals(24000L, quote.totalCents());
        })
        .verifyComplete();
~~~

This snippet assumes the `Quote` record and static import `assertEquals`, as in the Section 7 project. `assertNext` consumes one value and lets you run multiple JUnit/AssertJ assertions. If an inner assertion fails, `StepVerifier` fails the test rather than swallowing the error.

### `expectNextCount` Checks Count Only

~~~java
StepVerifier.create(Flux.just("A", "B", "C"))
        .expectNextCount(3)
        .verifyComplete();
~~~

It proves three `onNext` signals arrived before completion, **not** that the three values were `A, B, C`. Use it when content is outside the contract or verified elsewhere; avoid overusing it since it weakens test strength.

### When an Array/Collection Is a **Single** Reactive Value

~~~java
Mono<java.util.List<String>> result =
        Mono.just(java.util.List.of("A", "B"));

StepVerifier.create(result)
        .assertNext(list -> {
            assertEquals(2, list.size());
            assertEquals("A", list.get(0));
        })
        .verifyComplete();
~~~

The publisher above emits **one `List`**, not two separate signals `onNext("A")` and `onNext("B")`. Only if the API is `Flux<String>` do you check elements individually. Distinguish **`Mono<List<T>>`** from **`Flux<T>`** so your scenario matches the type and signal count.

## 5. Verifying Completion: `onComplete` Does Not Mean "Has Data"

A `Mono<T>` can:

- Emit **one T** then complete;
- Complete **empty**;
- Error **without a value**.

Therefore, tests must clarify the contract:

| Contract | Appropriate Scenario |
| --- | --- |
| Must return one quote | `expectNext(expectedQuote).verifyComplete()` |
| Not found → empty completion | `verifyComplete()` with **no `expectNext`** |
| Not found → error | `verifyError(NotFoundException.class)` |
| Returns multiple items in order | `expectNext(...).verifyComplete()` |
| Returns 0 or more items, count known | `expectNextCount(n).verifyComplete()` when n is known |
| Long-lived stream with no natural completion | `thenCancel().verify()` as appropriate |

Common pitfall: testing a `Mono<Order>` repository by writing only:

~~~java
StepVerifier.create(repository.findById("42"))
        .verifyComplete();
~~~

If the repository returns empty due to a buggy query, the test still passes. When the contract states **Order 42 must be found**, assert the exact ID and key fields with `expectNext`/`assertNext` before `verifyComplete`.

A test can also fail by assuming a publisher completes when the API is **designed as a continuous stream** (e.g., an event subscription). In that case, the test should check a bounded slice of data and cancel, or apply limits in production logic per requirements; do not demand a non-existent completion.

## 6. Verifying Errors: `onError` Is a Terminal Signal

In Reactor, many errors arise **inside the pipeline upon subscription**, rather than being thrown directly on the line that creates the publisher. For example:

~~~java
Mono<Integer> division =
        Mono.fromCallable(() -> 10 / 0);

StepVerifier.create(division)
        .verifyError(ArithmeticException.class);
~~~

This snippet is valid Java method-body code with `Mono` and `StepVerifier` imports. The division sits inside `fromCallable`, executes on subscribe, and the error is converted into `onError(ArithmeticException)`. Testing with `assertThrows(ArithmeticException.class, () -> division)` **misses the mark**, because that lambda only returns the `Mono` object without running the calculation.

### `verifyError(Class)` — Right Error Type

~~~java
StepVerifier.create(Mono.error(
        new IllegalArgumentException("invalid")))
        .verifyError(IllegalArgumentException.class);
~~~

Checks the exception type and error terminal signal, but **does not check the message**.

### `expectErrorMatches` — Right Type and Error Characteristics

~~~java
StepVerifier.create(Mono.error(
        new IllegalArgumentException("quantity must be positive")))
        .expectErrorMatches(error ->
                error instanceof IllegalArgumentException
                        && "quantity must be positive"
                                .equals(error.getMessage()))
        .verify();
~~~

The predicate should test meaningful conditions—never write `error -> true`, which passes for every error. Avoid asserting full stack traces or volatile internal messages if they are not part of the contract; check the error class, business status/code, or stable payload.

### `expectErrorSatisfies` — Multiple Assertions on the Error

~~~java
StepVerifier.create(Mono.error(
        new IllegalArgumentException("sku is required")))
        .expectErrorSatisfies(error -> {
            assertInstanceOf(IllegalArgumentException.class, error);
            assertEquals("sku is required", error.getMessage());
        })
        .verify();
~~~

This snippet needs the corresponding JUnit Jupiter static imports. It is the preferred way to verify multiple conditions on a terminal error. **Do not append `expectComplete()`**, because error is already terminal.

### Some Values Can Emit Before an Error

~~~java
Flux<String> result = Flux.concat(
        Flux.just("FIRST"),
        Flux.error(new IllegalStateException("upstream failed")));

StepVerifier.create(result)
        .expectNext("FIRST")
        .verifyError(IllegalStateException.class);
~~~

The test proves **`FIRST` was emitted before the error**. If the requirement says "on error, emit no data at all", such a pipeline violates it and needs different logic or a clarified contract. With `Flux`, **partial emissions followed by an error** are possible; tests should not assume the entire stream is an atomic transaction.

### Errors Handled by `onErrorResume` Are No Longer Terminal Errors

~~~java
Mono<String> result =
        Mono.<String>error(new IllegalStateException("temporary"))
                .onErrorResume(ex -> Mono.just("fallback"));

StepVerifier.create(result)
        .expectNext("fallback")
        .verifyComplete();
~~~

Because `onErrorResume` **switches the error to another publisher**, downstream observes the `"fallback"` value followed by completion. A test downstream of recovery should not expect `verifyError`. If auditing or logging the error before recovery is required, verify that side effect separately at the appropriate boundary.

**Do not swallow errors indiscriminately.** `onErrorResume(ex -> Mono.empty())` turns every error into an empty completion if the predicate is unconstrained. A test writing only `verifyComplete()` would stay green even when business logic breaks. Write dedicated tests for both error and recovery branches, and only fall back for permitted error types.

## 7. Complete Project: Java 17 + Spring Boot + Reactor Test

This project includes a service calculating order pricing in cents (using `long` integers), a small WebFlux controller, and JUnit tests. All Java classes belong to package `com.example.reactive`.

**Service contract:**

- A valid line has non-blank `sku`, `quantity > 0`, and `unitPriceCents >= 0`.
- The line total is `quantity × unitPriceCents` and must not overflow `long`.
- `quote(line)` returns **`Mono<Quote>` with one Quote then completes**, or `onError` on invalid input.
- `quoteAll(lines)` returns `Flux<Quote>` **in input order**, stopping with `onError` when an invalid element is encountered.
- A valid empty list → empty completing `Flux`.
- `quoteOrDefault` only falls back on `IllegalArgumentException` to a defined Quote; **`ArithmeticException` on overflow is not swallowed**.

### 7.1. Directory Structure

~~~text
reactor-stepverifier-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/reactive/
    │   ├── ReactorDemoApplication.java
    │   ├── PricingService.java
    │   └── QuoteController.java
    └── test/java/com/example/reactive/
        ├── PricingServiceStepVerifierTest.java
        └── QuoteControllerWebFluxTest.java
~~~

The Gradle Wrapper should come from the repository or be generated using a compatible installed Gradle version. `gradle-wrapper.jar` is a binary file—do not hand-copy its contents. If working in a module that already has a Wrapper, use the repo's version.

**`settings.gradle`**

~~~groovy
rootProject.name = 'reactor-stepverifier-demo'
~~~

**`build.gradle`** (Groovy DSL):

~~~groovy
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
}
~~~

`spring-boot-starter-webflux` brings in Reactor Core and Spring WebFlux. `spring-boot-starter-test` brings Spring Test/JUnit libraries; `reactor-test` is **explicitly declared** for `StepVerifier`. Spring Boot 3.3.5 dependency management aligns compatible Reactor/JUnit versions, so do not pin a `reactor-test` version different from `reactor-core`.

For Spring Boot 4 or newer Reactor trains, use dependencies and test starters matching the actual version; this is an **example for Boot 3.3.5**, not an instruction to alter an existing repository's versions.

### 7.2. Spring Boot Application

**`src/main/java/com/example/reactive/ReactorDemoApplication.java`**

~~~java
package com.example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactorDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactorDemoApplication.class, args);
    }
}
~~~

The Boot application sits in the same root package as the controller and service. When running only the **unit test `PricingServiceStepVerifierTest`**, `SpringApplication.run` and an application context are not needed. When running `@WebFluxTest` in Section 7.5, Spring boots a **WebFlux slice** to test mappings and JSON.

### 7.3. Real Reactive Service

**`src/main/java/com/example/reactive/PricingService.java`**

~~~java
package com.example.reactive;

import java.util.List;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public final class PricingService {

    public record OrderLine(
            String sku,
            int quantity,
            long unitPriceCents) {
    }

    public record Quote(String sku, long totalCents) {
    }

    public Mono<Quote> quote(OrderLine line) {
        return Mono.defer(() -> {
            if (line == null) {
                return Mono.error(new IllegalArgumentException(
                        "line is required"));
            }
            if (line.sku() == null || line.sku().isBlank()) {
                return Mono.error(new IllegalArgumentException(
                        "sku is required"));
            }
            if (line.quantity() <= 0) {
                return Mono.error(new IllegalArgumentException(
                        "quantity must be positive"));
            }
            if (line.unitPriceCents() < 0) {
                return Mono.error(new IllegalArgumentException(
                        "price must be non-negative"));
            }

            // Long overflow is converted to onError by Reactor.
            long total = Math.multiplyExact(
                    (long) line.quantity(),
                    line.unitPriceCents());

            return Mono.just(new Quote(line.sku(), total));
        });
    }

    public Flux<Quote> quoteAll(List<OrderLine> lines) {
        return Flux.defer(() -> {
            if (lines == null) {
                return Flux.error(new IllegalArgumentException(
                        "lines is required"));
            }

            // concatMap preserves output order and emits an error
            // when an invalid line is encountered.
            return Flux.fromIterable(lines)
                    .concatMap(this::quote);
        });
    }

    public Mono<Quote> quoteOrDefault(OrderLine line) {
        return quote(line)
                .onErrorResume(
                        IllegalArgumentException.class,
                        error -> Mono.just(new Quote("DEFAULT", 0L)));
    }
}
~~~

**Point-by-point explanation:**

- `Mono.defer` postpones publisher creation and execution until subscription time. If `Math.multiplyExact` throws `ArithmeticException` inside the callback, Reactor translates it to `onError`; `quote(...)` does not throw synchronously before returning the Mono.
- Validation produces `Mono.error(...)` with deterministic messages, enabling tests to assert the **exact reason** rather than just any error.
- `concatMap(this::quote)` subscribes to each line sequentially, so outputs appear in input order. Replacing it with `flatMap` over asynchronous publishers could scramble ordering, requiring contract and test updates.
- `quoteAll(List.of())` creates a Flux with zero items that completes normally, not an error.
- `onErrorResume(IllegalArgumentException.class, ...)` handles only validation errors. Overflow (`ArithmeticException`) still propagates downstream as `onError`.
- Calculating money in **cents** instead of `double` avoids floating-point rounding drift in this demo; real financial applications need full specification of units, rounding, bounds, and overflow protection.

### 7.4. Testing Reactive Logic with StepVerifier

**`src/test/java/com/example/reactive/PricingServiceStepVerifierTest.java`**

~~~java
package com.example.reactive;

import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import com.example.reactive.PricingService.OrderLine;
import com.example.reactive.PricingService.Quote;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

class PricingServiceStepVerifierTest {

    private final PricingService service = new PricingService();

    @Test
    void quoteEmitsOneValueThenCompletes() {
        Mono<Quote> result =
                service.quote(new OrderLine("BOOK", 2, 12000L));

        StepVerifier.create(result)
                .expectNext(new Quote("BOOK", 24000L))
                .verifyComplete();
    }

    @Test
    void quoteCanBeCheckedWithPredicate() {
        StepVerifier.create(
                service.quote(new OrderLine("PEN", 3, 250L)))
                .expectNextMatches(quote ->
                        "PEN".equals(quote.sku())
                                && quote.totalCents() == 750L)
                .verifyComplete();
    }

    @Test
    void quoteCanBeCheckedWithSeveralAssertions() {
        StepVerifier.create(
                service.quote(new OrderLine("BAG", 1, 500L)))
                .assertNext(quote -> {
                    assertEquals("BAG", quote.sku());
                    assertEquals(500L, quote.totalCents());
                })
                .verifyComplete();
    }

    @Test
    void quoteAllEmitsValuesInInputOrderThenCompletes() {
        List<OrderLine> lines = List.of(
                new OrderLine("PEN", 1, 250L),
                new OrderLine("BOOK", 2, 12000L));

        StepVerifier.create(service.quoteAll(lines))
                .expectNext(
                        new Quote("PEN", 250L),
                        new Quote("BOOK", 24000L))
                .verifyComplete();
    }

    @Test
    void emptyListCompletesWithoutValues() {
        StepVerifier.create(service.quoteAll(List.of()))
                .verifyComplete();
    }

    @Test
    void invalidQuantityEmitsErrorWithoutValue() {
        StepVerifier.create(
                service.quote(new OrderLine("BOOK", 0, 12000L)))
                .expectErrorMatches(error ->
                        error instanceof IllegalArgumentException
                                && "quantity must be positive"
                                        .equals(error.getMessage()))
                .verify();
    }

    @Test
    void invalidSkuHasSpecifiedErrorMessage() {
        StepVerifier.create(
                service.quote(new OrderLine("  ", 1, 100L)))
                .expectErrorSatisfies(error -> {
                    assertInstanceOf(
                            IllegalArgumentException.class, error);
                    assertEquals(
                            "sku is required", error.getMessage());
                })
                .verify();
    }

    @Test
    void firstValidLineMayArriveBeforeNextLineErrors() {
        List<OrderLine> lines = List.of(
                new OrderLine("PEN", 1, 250L),
                new OrderLine("BOOK", -1, 100L));

        StepVerifier.create(service.quoteAll(lines))
                .expectNext(new Quote("PEN", 250L))
                .verifyError(IllegalArgumentException.class);
    }

    @Test
    void arithmeticOverflowBecomesErrorSignal() {
        StepVerifier.create(
                service.quote(new OrderLine(
                        "BIG", 2, Long.MAX_VALUE)))
                .verifyError(ArithmeticException.class);
    }

    @Test
    void validationFailureCanRecoverToFallback() {
        StepVerifier.create(
                service.quoteOrDefault(new OrderLine(
                        "BOOK", 0, 100L)))
                .expectNext(new Quote("DEFAULT", 0L))
                .verifyComplete();
    }

    @Test
    void overflowIsNotSwallowedByValidationFallback() {
        StepVerifier.create(
                service.quoteOrDefault(new OrderLine(
                        "BIG", 2, Long.MAX_VALUE)))
                .verifyError(ArithmeticException.class);
    }

    @Test
    void nullListEmitsValidationError() {
        StepVerifier.create(service.quoteAll(null))
                .verifyError(IllegalArgumentException.class);
    }

    @Test
    void zeroInitialDemandRequiresExplicitRequests() {
        StepVerifier.create(Flux.range(1, 3), 0)
                .expectSubscription()
                .thenRequest(2)
                .expectNext(1, 2)
                .thenRequest(1)
                .expectNext(3)
                .verifyComplete();
    }

    @Test
    void virtualTimeChecksDelayWithoutRealHour() {
        StepVerifier.withVirtualTime(
                () -> Mono.delay(Duration.ofHours(1))
                          .map(tick -> "sent"))
                .expectSubscription()
                .expectNoEvent(Duration.ofMinutes(59))
                .thenAwait(Duration.ofMinutes(1))
                .expectNext("sent")
                .verifyComplete();
    }

    @Test
    void emptyMonoHasCompletionButNoNextValue() {
        StepVerifier.create(Mono.<String>empty())
                .verifyComplete();
    }

    @Test
    void infiniteFluxCanBeCancelled() {
        StepVerifier.create(Flux.never())
                .expectSubscription()
                .thenCancel()
                .verify();
    }

    @Test
    void emittedValueCanBeFollowedByErrorNotComplete() {
        Flux<String> source = Flux.concat(
                Flux.just("FIRST"),
                Flux.error(new IllegalStateException("upstream failed")));

        StepVerifier.create(source)
                .expectNext("FIRST")
                .verifyError(IllegalStateException.class);
    }
}
~~~

**This class has 17 `@Test` methods in total.** It uses no `@SpringBootTest`, Mockito, or HTTP port because its focus is testing a Java service's logic **and Reactor signals**. The `PricingService` object is a real instance, not mocked, so changing `quantity × unitPrice` to addition causes the pricing tests to fail.

### Explanation of Test Groups

| Group | Representative Method | Contract Protected |
| --- | --- | --- |
| Value + complete | `quoteEmitsOneValueThenCompletes` | One exact Quote, no extra values, finishes successfully |
| Predicate | `quoteCanBeCheckedWithPredicate` | Quote properties satisfy business rules |
| Multiple assertions | `quoteCanBeCheckedWithSeveralAssertions` | Both SKU and total amount are accurate |
| Multiple values in order | `quoteAllEmitsValuesInInputOrderThenCompletes` | Each Quote is correct and order is preserved |
| Empty completion | `emptyListCompletesWithoutValues` | Empty order list still finishes cleanly |
| Validation error | `invalidQuantityEmitsErrorWithoutValue` | Invalid quantity reports error without emitting Quote |
| Error details | `invalidSkuHasSpecifiedErrorMessage` | Appropriate error type and message |
| Value then error | `firstValidLineMayArriveBeforeNextLineErrors` | `Flux` may emit partial results before terminal error |
| Overflow | `arithmeticOverflowBecomesErrorSignal` | Does not return corrupt total on `long` overflow |
| Recovery | `validationFailureCanRecoverToFallback` | Validation error converts to fallback and completes |
| Unrecovered error | `overflowIsNotSwallowedByValidationFallback` | Does not swallow overflow error outside fallback scope |
| Null input | `nullListEmitsValidationError` | Error flows via `onError` instead of returning a null Flux |
| Backpressure | `zeroInitialDemandRequiresExplicitRequests` | Emits `onNext` only upon demand; exact count |
| Virtual time | `virtualTimeChecksDelayWithoutRealHour` | Does not emit before 1 hour and emits after advancing virtual time |
| Empty Mono | `emptyMonoHasCompletionButNoNextValue` | Completion is not equivalent to emitting a value |
| Cancellation | `infiniteFluxCanBeCancelled` | Cleanly ends testing a stream with no natural terminal |
| Partial result + error | `emittedValueCanBeFollowedByErrorNotComplete` | Error is a distinct terminal signal, not complete |

In `firstValidLineMayArriveBeforeNextLineErrors`, `concatMap` guarantees the first item emits before the second line causes an error. If the code switches to a concurrent operator like `flatMap` and sources become asynchronous, ordering can change; in that case, tests must reflect the real contract (whether order is required or not) rather than blindly loosening matchers to stay green.

### 7.5. WebFlux Controller and Separate HTTP Slice Test

`StepVerifier` verifies a `Publisher`, but it **does not check HTTP routing, status codes, or JSON serialization**. To illustrate the difference, we add a controller and a `WebTestClient` test.

**`src/main/java/com/example/reactive/QuoteController.java`**

~~~java
package com.example.reactive;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/quotes")
public class QuoteController {

    private final PricingService pricingService;

    public QuoteController(PricingService pricingService) {
        this.pricingService = pricingService;
    }

    @GetMapping("/{sku}")
    public Mono<PricingService.Quote> quote(
            @PathVariable("sku") String sku,
            @RequestParam("quantity") int quantity,
            @RequestParam("unitPriceCents") long unitPriceCents) {

        return pricingService.quote(
                new PricingService.OrderLine(
                        sku, quantity, unitPriceCents));
    }
}
~~~

The controller returns `Mono<Quote>` for WebFlux to serialize when the publisher emits a value and completes. When the publisher emits `onError`, Spring WebFlux needs an exception handler/error-handling policy to determine the desired HTTP status/body. **Do not assume "`IllegalArgumentException` inside a Mono always becomes 400"** without exception mapping: the default application behavior may return a server error depending on configuration.

**`src/test/java/com/example/reactive/QuoteControllerWebFluxTest.java`**

~~~java
package com.example.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(QuoteController.class)
@Import(PricingService.class)
class QuoteControllerWebFluxTest {

    @Autowired
    private WebTestClient client;

    @Test
    void httpResponseContainsCalculatedQuote() {
        client.get()
                .uri(
                    "/api/quotes/BOOK"
                    + "?quantity=2&unitPriceCents=12000")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.sku").isEqualTo("BOOK")
                .jsonPath("$.totalCents").isEqualTo(24000);
    }
}
~~~

**`@WebFluxTest`** boots the WebFlux slice and configures `WebTestClient` without needing a real HTTP server port. Since regular services are not automatically scanned in the slice, `@Import(PricingService.class)` supplies the real implementation to test the controller. This test proves request mapping and JSON serialization succeed; it **does not replace** the 17 `StepVerifier` tests covering validation, error, empty, and cancellation branches.

**Project test count:** 17 test methods from `PricingServiceStepVerifierTest` + 1 test in `QuoteControllerWebFluxTest` = **18 test methods**, with no `@ParameterizedTest`. When all files are created properly and dependencies are valid, **18 tests are expected to pass**. This is an expected result based on the code, not an observed run captured from a learner's environment.

## 8. Running the Project and Reading Reports

In the root directory are `gradlew`/`gradlew.bat`:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run only the `StepVerifier` unit tests:

~~~bash
./gradlew test --tests 'com.example.reactive.PricingServiceStepVerifierTest'
~~~

Run only the WebFlux slice:

~~~bash
./gradlew test --tests 'com.example.reactive.QuoteControllerWebFluxTest'
~~~

Typical Gradle reports:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.reactive.PricingServiceStepVerifierTest.xml
    └── TEST-com.example.reactive.QuoteControllerWebFluxTest.xml
~~~

There are no `System.out.println` statements in the runnable tests; **there is no fixed business stdout**. Gradle may report `BUILD SUCCESSFUL` and cache the task as `UP-TO-DATE` on re-runs. To force re-execution during investigation, run:

~~~bash
./gradlew test --rerun-tasks
~~~

To generate the Gradle Wrapper for a demo project when a compatible Gradle is installed, for example:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Then maintain Wrapper files per repository policy. The Java toolchain requires an available JDK 17 or toolchain provisioning; the Wrapper alone does not guarantee a suitable JDK. In real projects, **use the Wrapper version standardized by your team** instead of upgrading Gradle just to copy an example.

If the build fails on the `reactor-test` dependency, check `testImplementation` and network/Maven repositories; if compilation fails on the controller test, ensure `spring-boot-starter-webflux` is present, not just `spring-boot-starter-web`. If 0 tests are reported, check the `src/test/java` path, `org.junit.jupiter.api.Test` import, and `useJUnitPlatform()`.

## 9. Backpressure: `request(n)` and StepVerifier

Reactive Streams lets a subscriber control how many items it is ready to receive via demand. By default, `StepVerifier.create(publisher)` requests an unbounded amount, fitting basic value tests. When you need to verify a publisher **does not emit `onNext` before demand**, use the overload with `initialRequest=0`:

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
        .expectSubscription()
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(1)
        .expectNext(3)
        .verifyComplete();
~~~

Walkthrough:

1. Subscribe with **0 initial item demand**.
2. `thenRequest(2)` requests two elements.
3. Expect `1`, then `2`.
4. `thenRequest(1)` grants additional demand.
5. Expect `3` and completion.

This test verifies how `Flux.range` honors requests. For a custom publisher, you must also guard against **emitting past demand**; `StepVerifier` detects protocol/request violations according to its checks, though complex concurrency/backpressure issues may require deeper verification.

**Do not use `initialRequest=0` followed by `expectNext(...)` while forgetting `thenRequest`**: a compliant publisher will emit nothing, leaving the test hanging for unrequested items. Use `verify(Duration)` or proper cancellation to avoid hanging CI jobs indefinitely.

### `thenCancel` Tests Streams Without Completion

~~~java
StepVerifier.create(Flux.never())
        .expectSubscription()
        .thenCancel()
        .verify();
~~~

`Flux.never()` emits neither values nor terminal signals. `thenCancel` is a subscriber action, not `onComplete`. The test above cannot use `verifyComplete()`, because the publisher **has no natural completion**.

With long-lived event streams, a realistic scenario is "receive 3 events, inspect payloads, then cancel". However, if using `Flux.interval`, control the scheduler/virtual time to avoid flaky tests due to real timing.

## 10. Virtual Time: Do Not Sleep in Real Time to Test Delays

A test covering timeouts, retries, or delays might logically wait 1 hour, yet CI cannot wait 1 hour for a single test. `StepVerifier.withVirtualTime` swaps the scheduler used by Reactor operators for a virtual-time scheduler within the scope of the test when configured properly.

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofHours(1)))
        .expectSubscription()
        .expectNoEvent(Duration.ofMinutes(59))
        .thenAwait(Duration.ofMinutes(1))
        .expectNext(0L)
        .verifyComplete();
~~~

**Easy-to-miss details:**

- **The Publisher must be created inside the supplier** `() -> Mono.delay(...)`. Creating `Mono.delay` **before enabling virtual time** can capture a real scheduler and cause the test to take an hour or hang.
- `expectSubscription()` should precede `expectNoEvent(...)` because subscription **is also an event** in the scenario; calling `expectNoEvent` right at the start fails upon seeing `onSubscribe`.
- `expectNoEvent(59 minutes)` asserts no `onNext`/terminal signal occurred in that span, whereas `thenAwait(1 minute)` merely **advances the clock** without asserting silence during that window.
- `Mono.delay` emits `0L` when the timer fires here; a business test with `map(tick -> "sent")` expects `"sent"`, as in the runnable project.
- Virtual time only works as expected when operators use virtualized schedulers. Manually created/started schedulers, real I/O, real sleeps, or HTTP networking do not turn into virtual time.
- Infinite chains or complex scheduled operators can deadlock if the scenario does not advance the clock in the right steps. Keep tests small and clear, and avoid creating global schedulers outside the supplier.

### Do Not Use `Thread.sleep` to Prove Reactive Timing

This pattern is slow and flaky:

~~~java
// Not a recommended testing strategy:
Thread.sleep(1000);
assertEquals("done", sharedState.get());
~~~

Besides wasting time, it depends on thread scheduling and does not directly verify `onNext`/`onError`/`onComplete`. Use `withVirtualTime` for scheduler-based Reactor operators; use test timeouts, injected clocks, or fakes when logic depends on external systems or clocks outside Reactor's control.

## 11. Timeouts on `verify()`

A pipeline might never terminate due to a bug, missing demand, or an unresponsive upstream. Many forms of `verify()`/`verifyComplete()` do not enforce a short CI deadline by default. When hanging is a risk, use the timeout overload:

~~~java
StepVerifier.create(Flux.just("A", "B"))
        .expectNext("A", "B")
        .expectComplete()
        .verify(Duration.ofSeconds(3));
~~~

This snippet needs Reactor/JDK imports. A 3-second timeout is merely illustrative for publishers **doing no I/O**. For real network integration tests, pick timeouts based on environment and SLAs. Too short a timeout causes CI flakiness; an unbounded wait turns reactive bugs into long-hung jobs.

A different approach for pipelines required to finish in 2 seconds is the `.timeout(Duration)` operator, which **alters the publisher's behavior** and produces a timeout error if slow — unlike **`StepVerifier`'s timeout**, which is a wall-clock guard for the test itself. Do not treat the two timeouts as serving the same goal.

### `StepVerifierOptions.scenarioName` and Diagnostic Labels

For long scenarios, `StepVerifier` supports naming the scenario or individual expectations (`as("...")` on supporting API points) so failures are easier to identify. Still, nice labels do not replace assertions. Prefer descriptive test method names: `firstValidLineMayArriveBeforeNextLineErrors` is clearer than `testFlux1`.

## 12. Publishers Controlled by You via `TestPublisher`

When you need to actively emit `onNext`, `onComplete`, or `onError` into an active pipeline subscription, `reactor-test` provides `TestPublisher`. It differs from `StepVerifier`:

- **`StepVerifier`** is the subscriber verifying received signals.
- **`TestPublisher`** is a test-controlled data source emitting signals.

Example:

~~~java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux())
        .then(() -> source.next("A", "B"))
        .expectNext("A", "B")
        .then(source::complete)
        .verifyComplete();
~~~

This snippet belongs inside a test method; add `import reactor.test.publisher.TestPublisher;`. `then(...)` runs the callback **after `StepVerifier` has subscribed**. Emitting `A`, `B`, and then completing is orchestrated inside the scenario itself, preventing tests from relying on thread sleeps or external events.

Error emission example:

~~~java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux())
        .then(() -> source.next(1))
        .expectNext(1)
        .then(() -> source.error(
                new IllegalStateException("broken")))
        .verifyError(IllegalStateException.class);
~~~

When testing operators like `retry`, `onErrorResume`, `switchIfEmpty`, or `takeUntilOther`, use `TestPublisher` or `Sinks` as appropriate. Do not use `TestPublisher` merely to replace `Flux.just("A")` in every test; it adds verbosity and can hurt readability.

**Warning:** `TestPublisher` also has special modes to simulate **specification-violating scenarios** for testing operator resilience. Do not enable noncompliant modes arbitrarily when testing normal publishers; they can produce signals that a valid publisher is forbidden from emitting.

## 13. Error Recovery and Operators That Easily Produce "False Green" Tests

When code has multiple error branches, these operators carry distinct semantics:

| Operator | Downstream Signal Path | Risk If Tests Are Weak |
| --- | --- | --- |
| `map(...)` throws exception | Usually turns into `onError` | Testing only valid inputs misses mapping errors |
| `onErrorResume(...)` | Switches error to another publisher | `verifyComplete` can mask errors if fallback is empty |
| `onErrorReturn(value)` | Replaces error with value then completes | Can treat dummy value as real business data |
| `onErrorMap(...)` | Changes error type/attributes, still `onError` | Tests check wrong class or skip error details |
| `switchIfEmpty(...)` | Fallback on **empty completion**, not `onError` | Confuses "not found" with "system failure" |
| `defaultIfEmpty(value)` | Emits value if upstream is empty | Test checks only completion without checking fallback value |
| `retry(n)` | Resubscribes on error, potentially repeating side effects | Test fails to check attempt count or retry condition |
| `onErrorContinue(...)` | Can skip failing elements in supporting operators | Data silently lost while weak count tests miss it |

A strong test suite distinguishes:

- **Success:** `onNext(expected) → onComplete`.
- **No valid data:** `onComplete` with no `onNext`, when permitted by the contract.
- **Contract error:** `onError` with the expected type/properties.
- **Recoverable error:** `onNext(fallback) → onComplete` without swallowing out-of-scope errors.
- **Error after partial data:** `onNext` emitted prior to `onError`, without assuming automatic rollback of already-delivered items.

### `switchIfEmpty` Does Not Run on Error

~~~java
Mono<String> source = Mono.<String>error(
        new IllegalStateException("db unavailable"));

Mono<String> fallback = source.switchIfEmpty(
        Mono.just("not-found"));

StepVerifier.create(fallback)
        .verifyError(IllegalStateException.class);
~~~

`switchIfEmpty` only reacts to **empty completion**, not errors. If an API needs to translate DB unavailability into a specific error code or fallback, use appropriate error-handling operators; do not rely on `switchIfEmpty` to catch errors.

### `onErrorResume` Must Test Both Matching and Non-Matching Branches

In the project, `quoteOrDefault` only catches `IllegalArgumentException`. `validationFailureCanRecoverToFallback` verifies the recovery path; `overflowIsNotSwallowedByValidationFallback` verifies `ArithmeticException` passes through. With only the fallback test, a buggy change to `onErrorResume(error -> Mono.just(DEFAULT))` would pass undetected.

## 14. `StepVerifier` and `WebTestClient` Are Different Testing Layers

A WebFlux controller can return `Mono<ResponseDto>` or `Flux<ResponseDto>`. There are two distinct goals:

| Goal | Use | What Does It Prove? |
| --- | --- | --- |
| What values the service emits | `StepVerifier` | `onNext`, types/values, ordering |
| Whether the service completes/errors properly | `StepVerifier` | Terminal signals |
| How the service handles delays/backpressure | `StepVerifier` + virtual time/demand | Reactive behavior |
| Whether the HTTP route works | `WebTestClient` | HTTP method/path/status |
| Whether the JSON response is valid | `WebTestClient` | Serialization, headers, JSON body |
| Security filters / HTTP validation | `WebTestClient` with proper test context | HTTP contract with filters/beans active |
| Real HTTP server on a port | `@SpringBootTest(RANDOM_PORT)` + client | Network/container behavior |
| Database / remote adapter connectivity | Corresponding integration tests | Real infrastructure within fixture scope |

`StepVerifier` **knows nothing about HTTP status 404 or 500**. A `Mono.error(new IllegalArgumentException(...))` is purely a **reactive-level error signal**. HTTP status and body come from controllers, exception handlers, Spring WebFlux, and error-handling configuration. Thus, service `StepVerifier` tests can pass while the HTTP API still returns the wrong status.

Conversely, a `WebTestClient` test checking only `expectStatus().isOk()` does not cover service error branches. Use each at the **right layer** instead of cramming every scenario into full-context tests.

### What Happens When a `Flux` Emits Partial Data Then Errors Over HTTP?

In reactive HTTP streaming, the server may have already sent headers and initial chunks before the source emits `onError`. Once headers/body are committed, the server cannot always change the HTTP status from 200 to 500 and send a clean JSON error payload at the end like a standard non-streaming response. That is why service tests must verify the **actual signal sequence**, while HTTP streaming tests must check real API protocol, framing, and error semantics.

## 15. Common Errors and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Test runs without checking anything | Only `StepVerifier.create(...)` without terminal + `verify` | End scenario with `verifyComplete`, `verifyError`, or `expect...().verify()` |
| Test passes even though Mono is empty when data was expected | Only used `verifyComplete()` | Add `expectNext(expected)`/`assertNext` |
| Test expects complete but receives `onError` | SUT/mapper/validation threw or emitted error | Check root cause; write dedicated error test if error is the contract |
| Test expects error but receives complete | `onErrorResume`/`onErrorReturn` recovered | Assert fallback/empty per contract, test unrecovered error paths |
| Test fails due to extra item | `expectNext` finished but source emitted another `onNext` | Fix source logic or update expectation if contract permits |
| Test fails due to ordering | Used `flatMap` with async processing | Check ordering requirements; use `concatMap` when order must be preserved |
| `verifyComplete` hangs | Flux never completes or source lacks demand | Use `thenCancel`, `thenRequest`, timeout, or inspect operators |
| Test puts `expectNoEvent` first and fails | Subscription itself is an observed signal | Call `expectSubscription()` first |
| Virtual time still waits in real time | Publisher/scheduler created outside supplier or uses custom scheduler | Build operators inside `withVirtualTime(() -> ...)`, check scheduler |
| `NoClassDefFoundError: StepVerifier` | Missing `reactor-test` on test classpath | Add test dependency, check exclusions/versions |
| `StepVerifier` complains about request count | `initialRequest=0` without `thenRequest` | Issue explicit demand matching expected items |
| `NullPointerException` with `Mono.just(null)` | Reactor forbids `null` `onNext` | Use `Mono.empty`/`justOrEmpty` or a status model |
| `assertThrows` catches no exception | Error happens on subscribe, not when creating the Mono | Use `verifyError`/`expectErrorMatches` |
| Test passes despite wrong service calculation | Mocked the publisher/service itself to return expected value | Use real service and independently derived expected values |
| Brittle error message tests | Asserting stack traces or internal strings | Check stable type/error codes, and messages only when contractual |
| WebFlux test returns 500 instead of 400 | Reactive `onError` not mapped to HTTP error | Add/test an exception handler; do not alter `StepVerifier` to hide it |
| Flaky CI due to `Thread.sleep` | Depends on real scheduling/time | Virtual time, controlled scheduler, or fake clock |
| `TestPublisher` emits before subscriber | Test emits before subscribe/`then` step | Use `then(() -> source.next(...))` after subscribe |
| Test fails on Boot context startup | Unnecessary full Spring context or missing bean | Unit test pure reactive service first; open context only for DI/WebFlux checks |
| Test only asserts `expectNextCount` | Ignores item content | Use `expectNext`, predicate, or `assertNext` when values matter |

### Workflow for Reading a `StepVerifier` Failure

1. Read **"expected next signal"** in the `AssertionError`: was the scenario expecting `onNext`, `onComplete`, or `onError`?
2. Read **"actual signal"**: was there an extra `onNext`, early complete, unexpected error, or no signal?
3. Check whether the publisher under test uses **lazy execution**: do data retrieval and mapping only run upon subscribe?
4. Inspect operators that **alter signal semantics**: `onErrorResume`, `switchIfEmpty`, `retry`, `take`, `concatMap`/`flatMap`.
5. If the test hangs, check **backpressure demand, completion, schedulers, and timeouts**.
6. If HTTP status differs from expectation, inspect WebFlux exception mapping and server behavior; `StepVerifier` only reflects the reactive source.
7. Introduce a small deliberate bug in code to confirm the relevant test turns red, then revert it. Never alter expected values merely to keep a test green.

## 16. Writing Tests Resilient to Refactoring

A good test should fail when the **signal contract** changes, yet stay green through valid code refactoring.

| Change | Desired Outcome |
| --- | --- |
| `quote` computes `2 × 12000` as `12002` | **Fail** due to different expected Quote |
| `quote` returns `Mono.empty()` for a valid line | **Fail** due to missing `onNext` |
| `quote` emits Quote then `onError` instead of complete | **Fail** due to wrong terminal signal |
| `quoteAll` swaps two Quotes when contract requires input order | **Fail** |
| `quoteAll` skips an invalid line and completes | **Fail** on test expecting `onError` |
| `quoteOrDefault` swallows overflow as well | **Fail** on unrecovered overflow test |
| Extract validation helpers into private methods keeping signals identical | **Pass** |
| Change how `Mono`/`Flux` is constructed while keeping signal count/order | **Pass** |
| Change internal log text not required by contract | **Pass** |
| Swap source for an infinite stream when contract must complete | **Fail/timeout**, then fix the source rather than deleting the completion assertion |

Avoid tests that merely mirror the implementation:

~~~java
// WEAK PATTERN: expected repeats the SUT's own formula.
long expected = quantity * unitPriceCents;
StepVerifier.create(service.quote(line))
        .expectNext(new Quote(sku, expected))
        .verifyComplete();
~~~

This is an illustrative snippet with pre-existing variables. Computing expected values is **not wrong in every situation**, but blindly copying production logic (especially buggy conditions or rounding) makes tests pass alongside bugs. Use confirmed business examples and independent edge cases such as `2 × 12000 = 24000`, `quantity=0` error, and `Long.MAX_VALUE × 2` overflow.

## 17. Self-Study Exercises

**Exercise A — empty branch:** Add `findQuoteById(String id)` returning `Mono.empty()` when the ID does not exist. Write one test expecting **empty completion** and one expecting the matching Quote when found. Ensure the found test does not rely solely on `verifyComplete()`.

**Exercise B — error before and after `onNext`:** Use `Flux.concat(Flux.just("A"), Flux.error(...))`. Write `expectNext("A")`, then `verifyError(IllegalStateException.class)`. Flip the concatenation order so the error happens before `A` and observe the test fail.

**Exercise C — message and type:** With `OrderLine("BOOK", 0, 100)`, use `expectErrorMatches` to verify both class and message. Change validation to return a different exception so the test fails, then revert.

**Exercise D — bounded fallback:** Change `quoteOrDefault` to fall back on every `Throwable`. Confirm the overflow test fails; restore `onErrorResume` to only recover the agreed validation error.

**Exercise E — virtual time:** Use `Mono.delay(Duration.ofHours(2))`. Test that no `onNext` arrives for 1 hour 59 minutes, then advance 1 minute and expect the value. Create the publisher inside the `withVirtualTime` supplier rather than creating a scheduler upfront.

**Exercise F — backpressure:** Use `Flux.range(1, 5)`, `initialRequest=0`, `thenRequest(3)`/`expectNext(1,2,3)` then `thenRequest(2)`/`expectNext(4,5)`, followed by completion. Explain why omitting the second request prevents the test from completing.

**Exercise G — controller boundary:** In `QuoteController`, add a `@RestControllerAdvice` mapping `IllegalArgumentException` to HTTP 400 with a stable JSON error code. Write a `WebTestClient` test for the 400 response while keeping the service `StepVerifier` test expecting `onError`. Explain why the two tests expect different outcomes at their respective layers.

**Exercise H — `TestPublisher`:** Create a `TestPublisher` source, emit one item, and then emit an error. Use `StepVerifier` to check the value then error, confirming no completion follows the error. Avoid emitting signals before `StepVerifier` subscribes.

**Exercise I — timeout:** Create `Flux.never()` and explain why `verifyComplete` is unsuitable. Use `thenCancel().verify()` to test cancellation, or a finite `verify(Duration)` if the test must fail on non-completion.

## 18. StepVerifier Testing Checklist

- [ ] Do I know whether the Publisher emits **value**, **empty complete**, or **error** according to contract?
- [ ] Does every scenario end with `verify`, `verifyComplete`, `verifyError`, or an equivalent triggering variant?
- [ ] When data is required, did I use `expectNext`/`assertNext` instead of just `verifyComplete`?
- [ ] For multiple values, did I verify count **and order** when required by contract?
- [ ] For errors, did I verify class/error code/stable message and avoid expecting `onComplete` after `onError`?
- [ ] Did I test both `onErrorResume` recovery and errors that **must not** be recovered?
- [ ] Did I distinguish `Mono<List<T>>` (one item) from `Flux<T>` (many items)?
- [ ] Did I avoid unnecessary `block()`, manual `subscribe()`, or `Thread.sleep` when `StepVerifier` can verify signals?
- [ ] With `initialRequest=0`, did I include `thenRequest(n)` before expecting data?
- [ ] With virtual time, were the publisher/timed operators created inside the supplier, with subscription expected before `expectNoEvent`?
- [ ] With infinite streams, did I use cancellation or explicit bounds instead of demanding non-existent completion?
- [ ] Do reactive service tests exercise real logic with expectations independent of the implementation?
- [ ] When verifying HTTP status/JSON, did I use `WebTestClient` or separate integration tests rather than inferring from `StepVerifier`?
- [ ] Are tests free of uncontrolled schedulers/time/networking wherever avoidable?
- [ ] Do Gradle/JUnit reports confirm the tests actually executed rather than relying on task caching?

## 19. Official References

Consult API docs matching your project's **actual Reactor and Spring Boot versions**. The runnable example uses Spring Boot 3.3.5, which manages a compatible Reactor 3.6.x train.

- [Project Reactor 3.6 — Reference: Testing](https://projectreactor.io/docs/core/3.6.8/reference/#testing): `StepVerifier` examples, terminal expectations, virtual time, and `TestPublisher`.
- [Project Reactor — StepVerifier API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): `create`, `withVirtualTime`, `expectNext`, `expectError`, `verify`.
- [Project Reactor — Reactor Test Reference](https://projectreactor.io/docs/core/release/reference/testing.html): using `reactor-test` and virtual time limitations.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@WebFluxTest`/`WebTestClient` testing and organizing integration tests.
- [Reactive Streams Specification](https://www.reactive-streams.org/): contract for subscribe/request/onNext/onError/onComplete/cancel.

**Remember:** `StepVerifier` does not merely ask "what value did Mono/Flux return?", it asks "does the **entire signal sequence** obey the contract?". Check `onNext` contents, counts and ordering, `onComplete` on success, and `onError` on failure; apply backpressure and virtual time when needed. Putting `verify` at the end of the scenario is mandatory for the check to actually run.
