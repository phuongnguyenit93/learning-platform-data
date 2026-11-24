# Verifying Data, Completion, Errors, and Verification Deadlines with Reactor StepVerifier

**Module:** Spring Framework – reactive  
**Parent topic:** Reactor Testing  
**Lesson:** Verifying Data, Completion, Errors, and Verification Deadlines

## Learning Objectives

After this lesson, you will be able to:

1. Read and test the Reactive Streams signal sequence: `onSubscribe` → multiple `onNext` → a single terminal signal `onComplete` or `onError`; distinguish subscriber-initiated `cancel`.
2. Use `reactor-test` and `StepVerifier` to verify values, ordering, item counts, predicates, and object properties.
3. Test normally completing streams, empty streams, failing streams, and streams that never terminate.
4. Distinguish `expectComplete().verify()`, `verifyComplete()`, `expectError(...).verify()`, and `verifyError(...)`.
5. Set a deadline on **test verification** using `verify(Duration)`, instead of letting CI hang indefinitely.
6. Understand how `verify(Duration)` differs from the `Mono.timeout(...)` or `Flux.timeout(...)` operators inside application code.
7. Write time-based tests with `expectNoEvent`, `thenAwait`, and `StepVerifier.withVirtualTime` without waiting real hours.
8. Test backpressure with an initial request of 0 and `thenRequest`, and test cancellation with `thenCancel`.
9. Run a Java 17+/Maven/JUnit 5/Spring Boot BOM test suite with deterministic results, without relying on fragile `Thread.sleep` timing.
10. Diagnose assertion failures, forgotten terminal expectations, under-requested demand, and misconfigured virtual time.

## 1. What Really Needs Testing: Signals, Not Just Data

Both `Mono<T>` and `Flux<T>` implement `Publisher<T>`. A publisher is not merely an "asynchronous return list"; it follows a **signal protocol** between publisher and subscriber.

Basic flow:

```text
Subscriber                                    Publisher
    |                                            |
    |---------- subscribe() -------------------->|
    |<--------- onSubscribe(subscription) -------|
    |---------- request(n) --------------------->|
    |<--------- onNext(item 1) ------------------|
    |<--------- onNext(item 2) ------------------|
    |<--------- onComplete() --------------------|
    |                                            |
```

On error:

```text
onSubscribe -> onNext(A) -> onNext(B) -> onError(exception)
```

There is no `onComplete` after `onError`. In a compliant subscription, `onComplete` and `onError` are mutually exclusive. `onNext` must not emit `null` according to the Reactive Streams contract.

A subscriber can also call `cancel`:

```text
onSubscribe -> request(2) -> onNext(A) -> onNext(B) -> cancel()
```

`cancel` is a request to stop the subscription, not a terminal signal sent by the publisher to the subscriber. Therefore, when testing stream cancellation, do not wait for `onComplete` after `cancel`.

### 1.1. Differences Between Mono and Flux

| Publisher | Number of `onNext` | Normal terminal | Example |
| --- | --- | --- | --- |
| `Mono.just("OK")` | 1 | `onComplete` | Object found. |
| `Mono.empty()` | 0 | `onComplete` | No data, yet no error. |
| `Mono.error(ex)` | 0 | `onError` | Lookup failure. |
| `Flux.just(1,2,3)` | 3 | `onComplete` | Ordered list. |
| `Flux.empty()` | 0 | `onComplete` | Empty result set. |
| `Flux.concat(Flux.just(1), Flux.never())` | At least 1 in example | Never terminates on its own | Stream stays open. |

**A very common misconception:** `Mono.empty()` is a successful completion, not an exception. If the business logic treats not-found as an error, the source or service must explicitly convert it to an error, such as `switchIfEmpty(Mono.error(new NotFoundException(...)))`; `StepVerifier` only verifies the actual contract that exists.

## 2. What Is StepVerifier and When Does It Run?

`StepVerifier` lives in the `io.projectreactor:reactor-test` artifact. It acts as a subscriber capable of expressing an **expectation script** and strictly comparing actual signals.

Workflow:

```text
1. Create the Mono/Flux to test
           |
           v
2. StepVerifier.create(publisher)
           |
           v
3. Declare each expectation
   expectNext / assertNext / expectComplete / expectError
           |
           v
4. Call verify() / verify(Duration)
           |
           v
5. StepVerifier subscribes, receives signals, compares,
   throws AssertionError on mismatch
```

Short example:

```java
Flux<String> names = Flux.just("An", "Bình", "Chi");

StepVerifier.create(names)
        .expectNext("An", "Bình", "Chi")
        .verifyComplete();
```

The three values are verified **in exact order**. `verifyComplete()` also confirms that the publisher emitted `onComplete`, not merely that three elements were emitted.

Do not forget the verify step:

```java
StepVerifier.create(Flux.just(1, 2))
        .expectNext(1, 2)
        .expectComplete();
// verify() not called yet: no verification is performed.
```

The `StepVerifier` builder only describes the scenario. The `verify...()` methods are where verification runs and blocks the test thread until completion, failure, scripted cancellation, or verification timeout.

## 3. Ways to Verify onNext Data

### 3.1. expectNext: Exact Values and Order

```java
StepVerifier.create(Flux.just(10, 20, 30))
        .expectNext(10)
        .expectNext(20, 30)
        .verifyComplete();
```

Verifies using the object's `equals` method. With Java records or value objects that properly implement `equals`, this is the simplest approach.

```java
record Product(long id, String name) {}

StepVerifier.create(Mono.just(new Product(7, "Keyboard")))
        .expectNext(new Product(7, "Keyboard"))
        .verifyComplete();
```

If a DTO class does not implement `equals` properly, two objects with identical fields may still be treated as unequal. In that case, use `assertNext` to inspect fields.

### 3.2. expectNextMatches: Verifying a Predicate

```java
StepVerifier.create(Flux.just(5, 12, 18))
        .expectNextMatches(n -> n > 0)
        .expectNextMatches(n -> n % 2 == 0)
        .expectNextMatches(n -> n >= 18)
        .verifyComplete();
```

The predicate must return `true` for the **exact next element**. An element arriving out of order or a predicate returning false fails the test. Do not use `expectNextMatches` to skip non-matching elements; it is **not `filter`**.

Use it when values have important properties but you do not want to enforce an exact object match, such as dynamically generated IDs, timestamps, or normalized data.

### 3.3. assertNext: Multiple Assertions on One Element

```java
StepVerifier.create(
        Mono.just(new Product(7, "Keyboard")))
        .assertNext(product -> {
            assertEquals(7L, product.id());
            assertEquals("Keyboard", product.name());
            assertTrue(product.name().length() > 3);
        })
        .verifyComplete();
```

`assertEquals` and `assertTrue` are JUnit assertions. AssertJ's `assertThat` can also be used. If an assertion inside the lambda fails, StepVerifier propagates the assertion error so the test fails.

`assertNext` works well when a DTO has many fields or needs business invariant checks. It is a readable alias for `consumeNextWith`.

### 3.4. expectNextCount: Verifying Element Count

```java
StepVerifier.create(Flux.range(1, 100))
        .expectNext(1)
        .expectNextCount(98)
        .expectNext(100)
        .verifyComplete();
```

`expectNextCount(98)` only confirms **98 subsequent emissions**, without checking their values. If individual element values matter, do not rely on count alone; combine with `expectNext`, `expectNextMatches`, or `assertNext`.

Each element is still consumed so the script can proceed to the terminal signal.

### 3.5. expectNextSequence: Verifying an Iterable

```java
List<String> expected = List.of("an", "binh", "chi");

StepVerifier.create(
        Flux.just("an", "binh", "chi"))
        .expectNextSequence(expected)
        .verifyComplete();
```

Checks each element in the order defined by the Iterable. This is helpful when expected data is pre-built from a fixture. If output order is not guaranteed (for example concurrent `flatMap`), choose an appropriate contract: sort before comparing if business rules allow, or collect into a set/collection and compare unordered. Never force an arbitrary order only to make tests flaky.

### 3.6. recordWith and consumeRecordedWith

When you need to inspect the entire group of items rather than just the count:

```java
StepVerifier.create(Flux.just("A", "B", "C"))
        .recordWith(ArrayList::new)
        .expectNextCount(3)
        .consumeRecordedWith(values -> {
            assertEquals(List.of("A", "B", "C"), values);
        })
        .verifyComplete();
```

`recordWith` starts a recording session for `onNext` data, and `consumeRecordedWith` ends recording and passes the collection to assertions. Remember to bound the number of items in the test; never record an infinite stream into a list.

The snippet requires importing `java.util.ArrayList` and `java.util.List` along with JUnit assertions.

## 4. Verifying Completion

### 4.1. expectComplete and verifyComplete

Two equivalent ways to require normal completion:

```java
StepVerifier.create(Flux.just(1, 2))
        .expectNext(1, 2)
        .expectComplete()
        .verify();
```

and:

```java
StepVerifier.create(Flux.just(1, 2))
        .expectNext(1, 2)
        .verifyComplete();
```

`verifyComplete()` is a shortcut combining `expectComplete()` followed by verify. If the publisher emits unexpected extra items, emits an error, or fails to complete, the test must fail.

### 4.2. Mono.empty and Flux.empty

```java
StepVerifier.create(Mono.<String>empty())
        .verifyComplete();

StepVerifier.create(Flux.<Integer>empty())
        .expectComplete()
        .verify();
```

Both tests succeed because the source emits `onComplete` with no `onNext`.

Do not write:

```java
StepVerifier.create(Mono.<String>empty())
        .expectNext("fallback")
        .verifyComplete();
```

This snippet is an **intentionally wrong** example: `Mono.empty()` does not emit `"fallback"`, so StepVerifier receives early completion and throws an assertion failure. To receive a fallback, change the **application code** with `defaultIfEmpty` or `switchIfEmpty` and then test the actual contract.

### 4.3. Verifying No Extra Values After Expected Data

`verifyComplete()` verifies that no additional `onNext` arrives before the terminal signal. For instance, `Flux.just(1,2,3)` cannot pass a scenario with only `expectNext(1,2).verifyComplete()` because element 3 arrives before `onComplete`.

Thus StepVerifier checks **results**, **ordering**, and **termination mode**, not merely an expected array.

## 5. Verifying Errors

### 5.1. expectError: Verifying a Terminal Error

```java
StepVerifier.create(
        Flux.just(1, 2)
                .concatWith(Mono.<Integer>error(
                        new IllegalArgumentException("bad input"))))
        .expectNext(1, 2)
        .expectError(IllegalArgumentException.class)
        .verify();
```

An error is terminal: there must be no `onComplete` after `onError`. Note that `Flux.error(...)` is used to **emit an error as a reactive signal**, unlike throwing an arbitrary exception before a publisher is even returned.

If a service throws synchronously at method invocation time, StepVerifier does not yet have a Publisher to subscribe to. When you need to test failure behavior *at subscription time*, use `Mono.defer`, `Flux.defer`, or `Mono.fromCallable` if that matches the contract.

### 5.2. expectErrorMessage: Verifying the Message

```java
StepVerifier.create(
        Mono.<String>error(
                new IllegalStateException("permission denied")))
        .expectErrorMessage("permission denied")
        .verify();
```

This only checks the message, without enforcing the exception type. For structured error codes, combine a predicate or consumer to check both type and fields.

### 5.3. expectErrorMatches: Throwable Predicate

```java
StepVerifier.create(
        Mono.<String>error(
                new IllegalArgumentException("age must be positive")))
        .expectErrorMatches(error ->
                error instanceof IllegalArgumentException
                && error.getMessage().contains("age"))
        .verify();
```

A predicate fits well when multiple error attributes matter. Avoid matching overly specific messages if they are unstable implementation details or localized strings.

### 5.4. expectErrorSatisfies: Explicit Assertions

```java
StepVerifier.create(
        Mono.<String>error(
                new IllegalStateException("invalid state")))
        .expectErrorSatisfies(error -> {
            assertInstanceOf(IllegalStateException.class, error);
            assertEquals("invalid state", error.getMessage());
        })
        .verify();
```

`assertInstanceOf` is a JUnit 5 assertion. Asserting errors by specific type or business error code is generally more resilient than checking stack traces.

### 5.5. verifyError and verifyErrorMessage

`verifyError(SomeException.class)` and `verifyErrorMessage("...")` are shortcuts when no steps precede the error.

```java
StepVerifier.create(
        Mono.<Integer>error(new ArithmeticException("/ by zero")))
        .verifyError(ArithmeticException.class);
```

When `onNext` signals precede the error, use `expectNext(...).expectError(...).verify()` to describe the full sequence. Do not write `verifyComplete()` for a publisher that emits an error; those are two distinct terminal contracts.

## 6. Verification Deadlines: Protecting Tests from Hanging

### 6.1. By Default verify May Wait Forever

According to Reactor Test, when no default timeout is configured, `verify()` and shortcuts like `verifyComplete()` can wait indefinitely. This is dangerous in CI if the source is `Flux.never()` or a scenario waits on demand that was never requested.

Trap example:

```java
StepVerifier.create(Flux.never())
        .expectComplete()
        .verify(); // May hang forever: source does not complete.
```

This is an **intentionally non-terminating example**. Do not put it into real tests without setting a deadline.

### 6.2. verify(Duration) Is a Deadline for Verification

```java
StepVerifier.create(Flux.just(1, 2, 3))
        .expectNext(1, 2, 3)
        .expectComplete()
        .verify(Duration.ofSeconds(2));
```

The `Duration.ofSeconds(2)` argument is the **maximum real time StepVerifier waits to execute the whole scenario**. If signals do not arrive in time, StepVerifier throws an `AssertionError` for the test. It does not turn the Publisher into `onError(TimeoutException)`, nor does it create a business timeout for production subscribers.

Distinction:

| Concept | Where does it live? | On expiration | Purpose |
| --- | --- | --- | --- |
| `verify(Duration)` | Reactor Test scenario | Test fails with `AssertionError` on verify timeout | Prevent hanging tests, set verification deadline. |
| `StepVerifier.setDefaultTimeout(Duration)` | Global setting for StepVerifiers created afterward | `verify` calls without a duration use this default | Consistent timeout policy across a test suite. |
| `Mono.timeout(Duration)` / `Flux.timeout(Duration)` | Publisher in application code | Cancels upstream and emits `TimeoutException` downstream if no fallback | Enforce business signal wait limits. |
| `thenAwait(Duration)` | A StepVerifier step | Waits in real time or advances the virtual clock | Give operations time to emit data. |
| `expectNoEvent(Duration)` | A StepVerifier step | Assertion fails if any signal occurs during that window | Ensure no signal arrives too early. |

`verify(Duration)` returns a `Duration` representing the real time spent verifying, not a value emitted by the source.

```java
Duration elapsed = StepVerifier.create(Mono.just("OK"))
        .expectNext("OK")
        .expectComplete()
        .verify(Duration.ofSeconds(2));

assertTrue(!elapsed.isNegative());
```

Do not assert exact millisecond timings because CI machines vary in speed; measure performance with dedicated benchmarks or metrics when needed.

### 6.3. Testing That Verify Timeout Actually Detects a Hanging Stream

```java
@Test
void verifyDeadlineRejectsNever() {
    AssertionError problem = assertThrows(AssertionError.class, () ->
            StepVerifier.create(Flux.<Integer>never())
                    .expectSubscription()
                    .expectComplete()
                    .verify(Duration.ofMillis(150)));

    assertNotNull(problem);
}
```

`Flux.never()` emits neither data nor complete/error, so StepVerifier times out according to the test deadline. `assertThrows` here is **a way to demonstrate hang detection**, not a production error to be ignored. The 150 ms deadline is only for the example; choose 1–5 seconds on heavily loaded CI if real async work is involved.

### 6.4. Default Timeout: Use Carefully Due to Global State

```java
StepVerifier.setDefaultTimeout(Duration.ofSeconds(5));
try {
    StepVerifier.create(Mono.just("OK"))
            .expectNext("OK")
            .verifyComplete();
} finally {
    StepVerifier.resetDefaultTimeout();
}
```

`setDefaultTimeout` affects StepVerifiers **created after that call**. Do not change the global default between tests running in parallel, as it can affect other tests. Prefer `verify(Duration)` per test or configure it in a controlled test bootstrap.

## 7. Time Inside a Publisher: Virtual Time

Operators like `delayElement`, `delayElements`, `interval`, `timeout`, and `retryWhen` can depend on a scheduler. Testing real time with `Thread.sleep(10_000)` is slow and prone to flakiness.

`StepVerifier.withVirtualTime` replaces normal schedulers with `VirtualTimeScheduler` and allows advancing logical time. Multi-day durations can be tested quickly without waiting real time.

### 7.1. Use a Supplier So the Source Is Created After Virtual Clock Activation

Right:

```java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofDays(1)))
        .expectSubscription()
        .thenAwait(Duration.ofDays(1))
        .expectNext(0L)
        .verifyComplete();
```

Do not create a scheduler-bound pipeline beforehand and simply return it from the Supplier:

```java
Mono<Long> tooEarly = Mono.delay(Duration.ofDays(1));

StepVerifier.withVirtualTime(() -> tooEarly)
        .expectSubscription()
        .thenAwait(Duration.ofDays(1))
        .expectNext(0L)
        .verifyComplete();
```

The second snippet is an **anti-pattern** shown to illustrate the risk; some operators capture the scheduler too early and will not be governed by the virtual clock. Create the publisher **inside the Supplier lambda**, or call a method invoked when the Supplier runs.

### 7.2. thenAwait: Letting Time Pass

```java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofHours(1)).take(3))
        .expectSubscription()
        .thenAwait(Duration.ofHours(3))
        .expectNext(0L, 1L, 2L)
        .verifyComplete();
```

`Flux.interval` emits 0, 1, 2 after 1, 2, 3 logical hours respectively. `thenAwait` advances the virtual clock to allow events to arrive and then continues verification. With finite sources and simple schedules, tests run fast. In real systems, if a source uses a custom scheduler not controlled by StepVerifier, virtual time results will not behave as expected.

### 7.3. expectNoEvent: Must Not Emit Early

```java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofHours(24)))
        .expectSubscription()
        .expectNoEvent(Duration.ofHours(23))
        .thenAwait(Duration.ofHours(1))
        .expectNext(0L)
        .verifyComplete();
```

The scenario requires:

1. Subscription occurs.
2. During the first 23 logical hours there is no `onNext`, `onError`, or `onComplete`.
3. After one more hour, `onNext(0L)` is received.
4. Finally it completes.

**Important trap:** `expectNoEvent` also counts `onSubscribe` as an event. If you put `expectNoEvent(...)` at the very start before `expectSubscription()`, the test can fail immediately upon subscribing. Write `expectSubscription().expectNoEvent(...)` when verifying a silent window after subscription.

`expectNoEvent` detects signals **arriving too early**. Conversely, `thenAwait` only lets time advance without claiming that no signals may be emitted during that interval.

### 7.4. Testing a Business Timeout Operator

Suppose the application has:

```java
Mono<Long> remoteLike =
        Mono.delay(Duration.ofSeconds(10))
                .timeout(Duration.ofSeconds(3));
```

Expectation: after three seconds with no item, the timeout operator emits `java.util.concurrent.TimeoutException`.

```java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofSeconds(10))
                .timeout(Duration.ofSeconds(3)))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(3))
        .expectError(TimeoutException.class)
        .verify();
```

Here the timeout is emitted by **application code**, not by `verify(Duration)`. Virtual time avoids waiting three real seconds. `TimeoutException` requires importing `java.util.concurrent.TimeoutException`.

You should add a real-time verification deadline when integrating multiple schedulers or external dependencies:

```java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofSeconds(10))
                .timeout(Duration.ofSeconds(3)))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(3))
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(5));
```

Now there are **two independent deadlines**: three virtual seconds for the business timeout and at most five real seconds to prevent the test from hanging. Do not confuse them.

## 8. Backpressure and Cancellation in StepVerifier

### 8.1. Testing request(n)

By default, StepVerifier usually requests enough demand to receive the sequence. To test backpressure, set the initial request to 0:

```java
StepVerifier.create(Flux.range(1, 5), 0)
        .expectSubscription()
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(3)
        .expectNext(3, 4, 5)
        .verifyComplete();
```

The stream is requested two elements in the first batch and three elements in the second. A demand-compliant publisher must not send `onNext` before positive demand exists. This scenario also verifies ordering.

If you omit `thenRequest(3)` while still expecting more items, the test may wait forever (or fail on the verify deadline). That is a test bug for not granting enough demand, not necessarily a production bug.

### 8.2. Intentional Cancellation

```java
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Integer> source = Flux.range(1, 100)
        .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source, 2)
        .expectNext(1, 2)
        .thenCancel()
        .verify();

assertTrue(cancelled.get());
```

`thenCancel` ends the scenario by cancelling the subscription. Do **not** write `expectComplete` after cancel. `doOnCancel` helps verify that the source observed the cancellation signal.

Do not use `thenCancel` to mask a publisher that ought to complete; if the business contract requires completion, use `verifyComplete` so tests catch hanging streams.

### 8.3. Testing Long-Lived Publishers

For `Flux.interval` or live streams that do not complete on their own, there are three common approaches:

- Verify the first N items and then `thenCancel()` if the contract is a long-lived subscription.
- Use `take(n)` in the pipeline under test if business logic only requires n items; downstream then sees complete while upstream receives cancel.
- Use `withVirtualTime` when behavior depends on a scheduler and time.

Always manage subscriptions so test schedulers or resources do not linger after tests finish. Never call `subscribe()` manually and forget to `dispose()`.

## 9. Naming Scenarios for Easier Failure Diagnostics

`StepVerifierOptions.create().scenarioName("...")` assigns a name to the scenario, while `as("...")` describes the most recent expectation.

```java
StepVerifier.create(
        Flux.just(10, 20),
        StepVerifierOptions.create()
                .scenarioName("two pricing values"))
        .expectNext(10)
        .as("first price")
        .expectNext(20)
        .as("second price")
        .verifyComplete();
```

Names help locate failures in CI logs. Note that if an `AssertionError` is thrown directly by JUnit/AssertJ inside `assertNext`, the StepVerifier description is not necessarily appended to the error message; write meaningful assertion messages as well.

## 10. Runnable Java 17 + Maven + JUnit 5 Project

The example below uses Java 17+, Maven, and the BOM from **Spring Boot 3.3.5** to align versions of Reactor, `reactor-core`, and `reactor-test`. It does not start a web server; the focus is testing a **service returning Mono/Flux**.

Structure:

```text
reactor-step-verifier-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   └── ReactiveExamples.java
    └── test/java/demo/
        └── ReactiveExamplesTest.java
```

### 10.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>reactor-step-verifier-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

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

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The Boot parent manages Java test dependency versions and configures surefire. `reactor-test` is used only in test scope; production code does not depend directly on StepVerifier. This project intentionally omits the WebFlux starter to avoid adding dependencies unrelated to publisher verification.

### 10.2. ReactiveExamples.java

```java
package demo;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class ReactiveExamples {

    public record Reading(String sensor, int value) {
    }

    public Flux<Reading> readings() {
        return Flux.just(
                new Reading("temp", 21),
                new Reading("temp", 22),
                new Reading("cpu", 66));
    }

    public Mono<Reading> firstBySensor(String sensor) {
        return readings()
                .filter(r -> r.sensor().equals(sensor))
                .next();
    }

    public Flux<Integer> numbers() {
        return Flux.range(1, 5);
    }

    public Flux<Integer> evenSquares() {
        return Flux.range(1, 6)
                .filter(n -> n % 2 == 0)
                .map(n -> n * n);
    }

    public Mono<String> emptyResult() {
        return Mono.empty();
    }

    public Flux<Integer> errorAfterTwo() {
        return Flux.just(1, 2)
                .concatWith(Mono.<Integer>error(
                        new IllegalArgumentException("bad input")));
    }

    public Mono<Long> delayedValue() {
        return Mono.delay(Duration.ofDays(1));
    }

    public Flux<Long> hourlyTicks() {
        return Flux.interval(Duration.ofHours(1)).take(3);
    }

    public Mono<Long> delayedWithTimeout() {
        return Mono.delay(Duration.ofSeconds(10))
                .timeout(Duration.ofSeconds(3));
    }

    public Flux<Integer> neverFinishes() {
        return Flux.just(1)
                .concatWith(Flux.<Integer>never());
    }

    public Flux<Integer> cancellableNumbers(
            AtomicBoolean cancelObserved) {
        return Flux.range(1, 100)
                .doOnCancel(() -> cancelObserved.set(true));
    }
}
```

Each method returns a lazy publisher. Methods using `Mono.delay` or `Flux.interval` construct the pipeline when invoked. Therefore, with virtual time, simply calling the method inside the `withVirtualTime` lambda is enough for the scheduler to be configured beforehand.

Example values are fixed so tests do not depend on a network, database, or system clock.

### 10.3. ReactiveExamplesTest.java

```java
package demo;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReactiveExamplesTest {

    private final ReactiveExamples examples = new ReactiveExamples();

    @Test
    void verifiesAllValuesAndComplete() {
        StepVerifier.create(examples.readings())
                .expectNext(
                        new ReactiveExamples.Reading("temp", 21),
                        new ReactiveExamples.Reading("temp", 22),
                        new ReactiveExamples.Reading("cpu", 66))
                .verifyComplete();
    }

    @Test
    void verifiesValuesWithPredicates() {
        StepVerifier.create(examples.readings())
                .expectNextMatches(r ->
                        "temp".equals(r.sensor()) && r.value() == 21)
                .expectNextMatches(r -> r.value() > 20)
                .expectNextMatches(r ->
                        "cpu".equals(r.sensor()) && r.value() >= 60)
                .verifyComplete();
    }

    @Test
    void verifiesMonoFieldsWithAssertNext() {
        StepVerifier.create(examples.firstBySensor("temp"))
                .assertNext(reading -> {
                    assertEquals("temp", reading.sensor());
                    assertEquals(21, reading.value());
                })
                .verifyComplete();
    }

    @Test
    void verifiesSequenceAndCount() {
        StepVerifier.create(examples.numbers())
                .expectNextSequence(List.of(1, 2, 3, 4, 5))
                .verifyComplete();

        StepVerifier.create(examples.evenSquares())
                .expectNext(4)
                .expectNextCount(1)
                .expectNext(36)
                .verifyComplete();
    }

    @Test
    void verifiesEmptyCompletion() {
        StepVerifier.create(examples.emptyResult())
                .verifyComplete();

        StepVerifier.create(examples.firstBySensor("unknown"))
                .verifyComplete();
    }

    @Test
    void verifiesErrorAfterTwoValues() {
        StepVerifier.create(examples.errorAfterTwo())
                .expectNext(1, 2)
                .expectErrorSatisfies(error -> {
                    assertInstanceOf(
                            IllegalArgumentException.class, error);
                    assertEquals("bad input", error.getMessage());
                })
                .verify(Duration.ofSeconds(2));
    }

    @Test
    void verifiesErrorByPredicate() {
        StepVerifier.create(examples.errorAfterTwo())
                .expectNext(1, 2)
                .expectErrorMatches(error ->
                        error instanceof IllegalArgumentException
                        && error.getMessage().contains("bad"))
                .verify(Duration.ofSeconds(2));
    }

    @Test
    void verifiesCompleteWithinDeadline() {
        Duration elapsed = StepVerifier.create(examples.numbers())
                .expectNext(1, 2, 3, 4, 5)
                .expectComplete()
                .verify(Duration.ofSeconds(2));

        assertTrue(!elapsed.isNegative());
    }

    @Test
    void verifierDeadlineRejectsNeverCompletingSource() {
        AssertionError problem = assertThrows(
                AssertionError.class, () ->
                        StepVerifier.create(
                                Flux.<Integer>never())
                                .expectSubscription()
                                .expectComplete()
                                .verify(Duration.ofMillis(150)));

        assertNotNull(problem);
    }

    @Test
    void verifiesBoundedDemand() {
        StepVerifier.create(examples.numbers(), 0)
                .expectSubscription()
                .thenRequest(2)
                .expectNext(1, 2)
                .thenRequest(3)
                .expectNext(3, 4, 5)
                .verifyComplete();
    }

    @Test
    void verifiesCancellationWasObservedUpstream() {
        AtomicBoolean cancelled = new AtomicBoolean();

        StepVerifier.create(
                        examples.cancellableNumbers(cancelled), 2)
                .expectNext(1, 2)
                .thenCancel()
                .verify();

        assertTrue(cancelled.get());
    }

    @Test
    void usesVirtualTimeInsteadOfWaitingADay() {
        StepVerifier.withVirtualTime(examples::delayedValue)
                .expectSubscription()
                .expectNoEvent(Duration.ofHours(23))
                .thenAwait(Duration.ofHours(1))
                .expectNext(0L)
                .verifyComplete();
    }

    @Test
    void verifiesScheduledFluxItemsWithVirtualTime() {
        StepVerifier.withVirtualTime(examples::hourlyTicks)
                .expectSubscription()
                .thenAwait(Duration.ofHours(3))
                .expectNext(0L, 1L, 2L)
                .verifyComplete();
    }

    @Test
    void verifiesPublisherTimeoutWithVirtualTime() {
        StepVerifier.withVirtualTime(
                        examples::delayedWithTimeout)
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(3))
                .expectError(TimeoutException.class)
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void namedScenarioIsMoreReadableOnFailure() {
        StepVerifier.create(
                        examples.numbers(),
                        StepVerifierOptions.create()
                                .scenarioName("numbers 1 to 5"))
                .expectNext(1)
                .as("first number")
                .expectNextCount(3)
                .expectNext(5)
                .verifyComplete();
    }
}
```

This is a standalone JUnit test class with 15 test cases. It checks:

- Record values, predicates, fields, ordering, and element counts.
- Empty Mono completing normally.
- Flux emitting data then failing.
- Verification completing within a deadline, and the deadline catching a never-completing source.
- Manual demand requests and cancellation observed upstream.
- Time-dependent data generation using a virtual scheduler.
- Publisher business timeout vs. StepVerifier timeout.
- Scenario names and expectation descriptions.

### 10.4. Running Maven

In the directory containing `pom.xml`:

```bash
mvn test
```

With JDK 17+, Maven, downloaded dependencies, and a proper environment, the expected result is **15 tests passed, 0 failures, 0 errors**. Logs can vary in build/plugin lines and timings, so there is no fixed stdout to copy verbatim.

Use the following command to run only that test class:

```bash
mvn -Dtest=ReactiveExamplesTest test
```

These commands run real JUnit tests; no Spring Boot HTTP server needs to start. To run in CI, add the project's build/test steps per your workflow.

### 10.5. Reading a Test Signal by Signal

Example testing values and completion:

```java
StepVerifier.create(Flux.just("A", "B"))
        .expectSubscription()
        .expectNext("A")
        .expectNext("B")
        .expectComplete()
        .verify(Duration.ofSeconds(2));
```

Logical order:

```text
1. Subscribe to Flux.just
2. Observe onSubscribe
3. Receive onNext("A") and compare
4. Receive onNext("B") and compare
5. Receive onComplete
6. Finish verify before 2 real seconds elapse
```

If the source returns `"B"` before `"A"`, the test fails at step 3. If the source emits an error instead of complete, the test fails at step 5. If the source does not terminate, the test fails when verify hits its deadline.

## 11. Quick API Selection Table

| Want to verify | How to express it |
| --- | --- |
| Exact values in order | `expectNext(v1, v2)` |
| Object fields | `assertNext(item -> assertEquals(...))` |
| Condition on the next element | `expectNextMatches(predicate)` |
| N elements, ignoring values | `expectNextCount(n)` |
| Expected list | `expectNextSequence(expected)` |
| Successful completion | `expectComplete().verify()` or `verifyComplete()` |
| Empty publisher completes | `StepVerifier.create(Mono.empty()).verifyComplete()` |
| Error by type | `expectError(Type.class).verify()` |
| Error by message | `expectErrorMessage("...").verify()` |
| Error by arbitrary logic | `expectErrorMatches(...)` or `expectErrorSatisfies(...)` |
| Prevent test from hanging | `expectComplete().verify(Duration.ofSeconds(2))` |
| Set default verify timeout | `StepVerifier.setDefaultTimeout(duration)` |
| No signals emitted during window t | `expectSubscription().expectNoEvent(t)` |
| Advance time | `thenAwait(t)` |
| Virtual time | `withVirtualTime(() -> publisher)` |
| Manual demand requests | `create(source, 0).thenRequest(n)` |
| Explicitly cancel subscription | `thenCancel().verify()` |
| Name the scenario | `StepVerifierOptions.scenarioName(...)`, `as(...)` |

This section is a quick reference, not a replacement for the explained examples above.

## 12. Real-World Pitfalls and How to Fix Them

### 12.1. Forgetting verify

**Wrong:**

```java
StepVerifier.create(service.fetch())
        .expectNext("OK")
        .expectComplete();
```

Without `verify`, the scenario never executes. **Right:** end with `verify()` or `verifyComplete()`.

### 12.2. Test Only Checks onNext Without Terminal

**Coverage flaw:** verifies one element without confirming whether the publisher completes or errors. If the contract is a single response, use `expectNext(expected).verifyComplete()`. If the contract is a long-lived stream, use a scenario with `thenCancel()` and document why completion is not awaited.

### 12.3. Using expectNext When DTO Lacks equals

**Symptom:** the object has the right fields, yet the test reports a mismatch. **Fix:** use a Java record/value object with proper `equals`, or `assertNext` to check fields. Never override `equals` arbitrarily just to make tests pass if doing so breaks business correctness.

### 12.4. Misunderstanding flatMap Ordering

`flatMap` can emit items from asynchronous tasks in completion order, not necessarily input order. If business logic guarantees order, use `concatMap` or `flatMapSequential` where appropriate and test the exact order; otherwise, collect and compare as a set/collection instead of forcing a flaky order.

### 12.5. Testing Flux.never with Unbounded verify()

**Symptom:** CI hangs. **Fix:** always set a `verify(Duration)` deadline when a source might not terminate; for intentionally live streams, use `thenCancel()` once enough data arrives or when the test window ends.

### 12.6. Calling expectNoEvent First

`expectNoEvent` treats `onSubscribe` as an event. **Fix:** `expectSubscription().expectNoEvent(...)`, or use `thenAwait(...)` if you only need time to pass.

### 12.7. Creating the Publisher Before withVirtualTime

**Symptom:** the test still waits in real time or hangs. **Fix:** create timers/intervals/delays inside the Supplier passed to `StepVerifier.withVirtualTime`. Check custom schedulers: virtual time does not automatically control executors outside Reactor.

### 12.8. Using Thread.sleep and Asserting Exact Timings

**Symptom:** slow and flaky tests under heavy CI load. **Fix:** test logic with virtual time, and give real integration tests suitable tolerances/timeouts; do not assert runtimes down to the millisecond.

### 12.9. Thinking verify Timeout Produces onError(TimeoutException)

**Wrong:** `verify(Duration.ofMillis(100))` does not cause a production publisher to emit `TimeoutException`. When the test deadline expires, StepVerifier throws `AssertionError`. To test a business timeout, actually add `timeout(Duration)` to the publisher and assert `expectError(TimeoutException.class)`.

### 12.10. Setting Default Timeout in Parallel Tests

`setDefaultTimeout` affects newly created StepVerifiers in the same JVM. If other tests run in parallel, they may inherit an unintended policy. Use a fixed configuration at the test suite level or prefer explicit deadlines on each `verify`.

### 12.11. Missing Demand in Backpressure Tests

**Wrong:** starting with `create(source, 0)` and immediately calling `expectNext(...)` without `thenRequest`; a backpressure-compliant source will emit nothing. **Fix:** explicitly write each `thenRequest(n)` before the items to check, followed by a terminal expectation or cancel.

### 12.12. Treating Cancel as Complete

After `thenCancel()`, do not expect `onComplete`. Cancellation is a subscriber-side signal. To test cleanup handling, place `doFinally`/`doOnCancel` before the cancellation point, or use an appropriate metric/probe.

### 12.13. Testing Errors Only by Message

Framework/library messages can change across versions. When a durable contract is needed, assert the exception type, business error code, and structured fields; only assert the message when it is an explicit contract.

### 12.14. Unexpected Extra Elements

`StepVerifier.create(Flux.just(1,2,3)).expectNext(1,2).verifyComplete()` must fail because item 3 arrives before completion. Do not "fix" it with `expectNextCount(1)` if business rules forbid extra items; the test is supposed to catch the bug.

### 12.15. Manual subscribe and Forgotten dispose

Do not write tests using `source.subscribe(...); Thread.sleep(...)` when StepVerifier can be used: async callbacks make failures hard to surface to the JUnit thread and easily leak subscriptions. StepVerifier provides clearer signal specification and time bounds.

## 13. Self-Check Questions

**Question 1.** What does StepVerifier verify besides data?  
**Answer:** Signal ordering, termination via complete/error or cancellation, demand/time, and verification deadlines.

**Question 2.** Is `Mono.empty` an `onError`?  
**Answer:** No. It emits `onComplete` without emitting `onNext`.

**Question 3.** Does `expectNextCount(10)` verify the value of each item?  
**Answer:** No; it only verifies the number of `onNext` emissions.

**Question 4.** When should `assertNext` be used instead of `expectNext`?  
**Answer:** When you want to check object properties or when a DTO lacks a suitable `equals`.

**Question 5.** How does `verifyComplete()` differ from `verifyError()`?  
**Answer:** `verifyComplete` requires `onComplete`; `verifyError` requires terminal `onError`.

**Question 6.** Why must `verify()` never be forgotten?  
**Answer:** Because the `expect...` methods only configure the scenario without subscribing or comparing signals.

**Question 7.** Does `verify(Duration)` turn the source into `Mono.timeout`?  
**Answer:** No. It bounds test execution time; a business timeout must live inside the publisher and can emit `TimeoutException`.

**Question 8.** Why does `withVirtualTime` take a Supplier?  
**Answer:** So the publisher and timers/schedulers are created after the virtual scheduler is activated.

**Question 9.** Does `expectNoEvent` count `onSubscribe`?  
**Answer:** Yes; typically place `expectSubscription()` before it.

**Question 10.** What does a backpressure test with initial request 0 need?  
**Answer:** It needs `thenRequest(n)` to grant demand per batch, or an intentional wait test proving the source does not exceed demand.

**Question 11.** How do you test a stream that intentionally runs forever?  
**Answer:** Receive the contracted number of items then `thenCancel()`, or use a timeout test; do not wait indefinitely on `verifyComplete`.

**Question 12.** Can `onComplete` follow `onError` on the same subscription?  
**Answer:** No. The two terminal signals are mutually exclusive.

## 14. Checklist Before Putting Tests into CI

- [ ] Tests have a final `verify()` or verify shortcut.
- [ ] A terminal `complete`, `error`, or `cancel` expectation matches the contract.
- [ ] Values and ordering are verified appropriately; do not only count elements when contents matter.
- [ ] Every potentially hanging source has `verify(Duration)` or a controlled test deadline.
- [ ] Time-based tests use `withVirtualTime` when dependent on Reactor schedulers and virtualizable.
- [ ] Time-dependent publishers/schedulers are created **inside the Supplier**.
- [ ] `expectNoEvent` tests place it after `expectSubscription`.
- [ ] Backpressure tests grant sufficient `thenRequest`.
- [ ] Cancellation tests do not expect `onComplete` and observe upstream at the right spot.
- [ ] No `Thread.sleep` and no leaked subscriptions.
- [ ] Expectations have names/descriptions when a suite has many similar cases.
- [ ] Test timeouts are not mistaken for production business timeouts.

## 15. Key Takeaways

- StepVerifier checks **both data and terminal signals**, not just return values.
- `expectNext` checks `equals` and order; `expectNextMatches` checks a predicate; `assertNext` checks fields; `expectNextCount` only counts.
- `verifyComplete` passes only if the publisher emits `onComplete` as scripted. `verifyError` passes only if it terminates with the expected `onError`.
- **Always set a verification deadline** for scenarios that might not finish; `verify(Duration)` is a test guard, not application timeout handling.
- `withVirtualTime` lets you test delay, interval, and timeout without waiting real time; remember to create the publisher inside the Supplier.
- `expectNoEvent` checks for a silent interval, whereas `thenAwait` only advances the clock.
- `thenRequest` tests backpressure; `thenCancel` tests cancelling an open stream.

## References

1. [Project Reactor – Testing (Reference Guide)](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier, virtual time, naming expectations, and reactor-test utilities.
2. [Project Reactor – StepVerifier API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): `create`, `withVirtualTime`, `verify(Duration)`, default timeout, and post-verification assertions.
3. [Project Reactor – StepVerifier.Step API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.Step.html): `expectNext`, `assertNext`, `expectNextMatches`, `expectNextCount`, `expectNextSequence`, `expectNoEvent`, `thenRequest`.
4. [Project Reactor – StepVerifier.LastStep API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.LastStep.html): `expectComplete`, `expectError`, `verifyComplete`, `verifyError`, `thenCancel`.
5. [Project Reactor – Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): `empty`, `error`, `delay`, `timeout`.
6. [Project Reactor – Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `range`, `interval`, `take`, `concatWith`.
7. [Reactive Streams 1.0.4 Specification](https://www.reactive-streams.org/): `Publisher`, `Subscriber`, `Subscription.request`, `Subscription.cancel`, and terminal signals.
