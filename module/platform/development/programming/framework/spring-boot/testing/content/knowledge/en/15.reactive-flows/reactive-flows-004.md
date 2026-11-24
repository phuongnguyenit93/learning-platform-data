# Virtual Time for Delay, Timeout, and Retry in Reactor/Spring Boot

> **Module:** Spring Boot – testing  
> **Topic:** Reactive Flows  
> **Focus:** Using `StepVerifier.withVirtualTime` and `VirtualTimeScheduler` to verify timing of `delay`, `timeout`, and `retryWhen` without waiting for a real clock to tick through seconds, minutes, or hours.

## 1. Why Are Time-Based Reactive Tests Often Difficult?

Reactive streams do not necessarily emit data immediately when a method is called. Many operators use a `Scheduler` to schedule future work:

- `Mono.delay(Duration)` emits a signal after a waiting period.
- `Mono#delayElement(Duration)` postpones emitting a single element.
- `Flux#delayElements(Duration)` spaces out emissions between elements.
- `Flux.interval(Duration)` emits sequential numbers at a steady cadence.
- `timeout(Duration)` turns into an error if no eligible signal arrives before the deadline.
- `retryWhen(Retry.fixedDelay(...))` waits between retry attempts when upstream fails.
- `Retry.backoff(...)` builds exponentially increasing waits, optionally with jitter.

A misguided test often looks like:

```java
Flux<String> events = service.events();
Thread.sleep(5000);
assertEquals(..., collectedEvents);
```

This snippet **only illustrates an anti-pattern**, not a standalone Java program. It has several flaws:

1. The test runs slowly—for the full duration of the wait.
2. CPU scheduling, CI load, and networking make sleeps flaky.
3. `Thread.sleep` does not automatically subscribe to a reactive publisher; without a subscriber, the pipeline may not even run.
4. If the test sleeps 5 seconds while buggy code emits at second 3, an assertion checking only the end state still passes.
5. When testing retries with multi-minute or multi-day backoffs, wall-clock tests become impractical.

**Virtual time** solves the part involving **Reactor's scheduling clock**: the test suite actively advances the clock from `t=0` to `t=5s`, `t=20s`, and so on without waiting in real time. It cannot fast-forward HTTP/network calls, JDBC, `Thread.sleep`, or any blocking operation not integrated with the virtual scheduler.

## 2. Mental Model: Real Time vs. Virtual Time

In Reactor, a time-based operator uses a `Scheduler` to schedule tasks in the future. With a real scheduler, tasks wake up according to the wall clock. With `VirtualTimeScheduler`, tasks are stored in a queue tagged with the virtual timestamp at which they should execute. The test calls `thenAwait` or `expectNoEvent` to advance the virtual clock to that point.

```text
                    REAL TIME

test subscribe    sleep/wait 5s       onNext("ready")
     |-------------------------------|
   wall 0s                        wall 5s

                    VIRTUAL TIME

test subscribe    advance virtual clock    onNext("ready")
     |.......................|
   virtual 0s             virtual 5s

    Actual wall-clock wait: usually tiny, not 5s.
```

Two notions of time must be kept distinct:

| Concept | Meaning | Use in Tests |
| --- | --- | --- |
| **Virtual clock** | The clock of `VirtualTimeScheduler` | Fast-forward `Duration` to trigger delayed tasks |
| **Wall-clock duration** | Real machine/CI elapsed time | Bound test hangs with `verify(Duration)` |
| **Scheduler** | Component executing/scheduling tasks | Time-based operators use an appropriate scheduler |
| **Subscription** | The `onSubscribe` signal starting the pipeline | Must occur before advancing and expecting signals |
| **Backpressure/request** | How many items the subscriber demands | Can affect `Flux.interval` and other publishers |
| **Cancellation** | Subscriber/timeout stopping a subscription | Not equivalent to upstream having succeeded |

**Principle:** a test does not only check *what value arrives at the end*; it can also verify **that nothing emits before a deadline**, **that an item emits right after advancing to a mark**, **how many times the source is subscribed to**, and **that on timeout the error, fallback, and cancellation are handled properly**.

## 3. How Does `StepVerifier.withVirtualTime` Work?

`StepVerifier` is a tool in the `reactor-test` module for asserting sequences of Reactive Streams signals: subscription, next value, completion, or error. When using:

```java
StepVerifier.withVirtualTime(() -> Mono.delay(Duration.ofDays(1)))
    .expectSubscription()
    .thenAwait(Duration.ofDays(1))
    .expectNext(0L)
    .verifyComplete();
```

the test does not wait 24 real hours. `withVirtualTime` installs `VirtualTimeScheduler` across Reactor's default managed scheduler factories; as a result, operators such as `Mono.delay`, `timeout`, and retry delays use the virtual clock.

**Two conditions determine success:**

1. Publishers/operators use the virtual clock rather than a pre-created real scheduler from elsewhere.
2. The Publisher must be **created inside the `Supplier` passed to `withVirtualTime`**, after the virtual scheduler has been installed.

### 3.1. Why Must the Argument Be a `Supplier`?

Misguided approach:

```java
// DO NOT build timed publishers before withVirtualTime:
Mono<Long> value = Mono.delay(Duration.ofHours(1));

StepVerifier.withVirtualTime(() -> value)
    .expectSubscription()
    .thenAwait(Duration.ofHours(1))
    .expectNext(0L)
    .verifyComplete();
```

This is an **anti-pattern**: it may capture a real scheduler during assembly and escape virtual-time control. Consequences include hangs, failures, or running in real time. Never rely on an accidental pass to conclude the design is sound.

Correct approach:

```java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofHours(1)))
    .expectSubscription()
    .thenAwait(Duration.ofHours(1))
    .expectNext(0L)
    .verifyComplete();
```

All construction of `Mono.delay` occurs **inside the lambda**, while the virtual scheduler is active.

If production code defines a method:

```java
Mono<String> messageAfter(Duration duration) {
    return Mono.just("ready").delayElement(duration);
}
```

then the test should invoke the method **inside the lambda**:

```java
StepVerifier.withVirtualTime(
        () -> service.messageAfter(Duration.ofHours(1)))
    .expectSubscription()
    .thenAwait(Duration.ofHours(1))
    .expectNext("ready")
    .verifyComplete();
```

These two method/test snippets are illustrative only. The full project in Section 6 uses `delayedGreeting`. A publisher constructed before the lambda may already hold a locked-in scheduler; using `Mono.defer` inside a service defers source creation until subscription when needed, though it cannot fix every eagerly initialized scheduler.

### 3.2. `expectSubscription` and `expectNoEvent`

`expectNoEvent(Duration)` asserts that **no events occur** during the given span. The `subscription` signal itself counts as an event.

Therefore:

```java
StepVerifier.withVirtualTime(() -> Mono.delay(Duration.ofSeconds(5)))
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(4))
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .verifyComplete();
```

accurately expresses the intent: stay silent for four virtual seconds after subscription, then emit `0L` and complete at the five-second mark.

Do not place `expectNoEvent(Duration)` as the very first step when the pipeline needs to subscribe: the immediate subscription signal will fail the assertion. Always call `expectSubscription()` first.

### 3.3. `thenAwait` vs. `expectNoEvent`

| API | Effect | Verifies Silence? |
| --- | --- | --- |
| `thenAwait(Duration)` | Advances clock / waits so signals can arrive | **No** |
| `expectNoEvent(Duration)` | Advances clock / waits while failing if any event arrives in that span | **Yes** |
| `expectNext(value)` | Requires an `onNext` with the specified value | Does not express a separate deadline |
| `expectNextCount(n)` | Requires `n` `onNext` signals | Does not protect individual values |
| `expectError(Class)` | Requires terminal error of matching type | Does not check message/cause unless asserted |
| `verifyComplete()` | Triggers verification and requires completion | Can wait forever if virtual clock is not advanced |

For example, proving "**no email is sent before 5 minutes**" requires `expectNoEvent` across the guarded window, not just `thenAwait` followed by a final assertion.

## 4. Not All Async Operations Run on Virtual Time

`StepVerifier.withVirtualTime` works when timed operators obtain their scheduler from Reactor's replaced `Schedulers` factories, typically `Schedulers.parallel()`. It **does not** automatically control:

- `Thread.sleep(5000)` inside `Mono.fromCallable`.
- HTTP calls from `WebClient` waiting on real DNS/sockets/servers.
- A manually created JDK `ScheduledExecutorService`/`Executor`.
- A `Schedulers.newSingle("external")` created prior to the lambda and passed explicitly to `delayElement(..., scheduler)`.
- SQL transactions, HTTP client/JDBC network timeouts, or external brokers.
- A hot source that already emitted data before the subscriber arrived.
- Side effects reading wall-clock time via `Instant.now()` or `System.currentTimeMillis()` instead of an injected `Clock`.

That is why this lesson targets **Reactor pipeline timing**. For real HTTP endpoints, virtual time suits the underlying service/operators; request/response integration tests can use a mock HTTP server or test container with short real timeouts. Never advance a virtual clock and claim real TLS, connection pools, or external providers timed out.

### 4.1. Virtual Time vs. Java Virtual Threads

Two easily confused terms:

- **Virtual time:** a test-controlled simulated clock, such as `VirtualTimeScheduler`.
- **Java virtual threads:** a lightweight JVM thread execution model (Java 21+) that does not make wait durations disappear.

Enabling virtual threads in an application does not make `Mono.delay(Duration.ofDays(1))` finish in milliseconds during a test. Conversely, a virtual scheduler does not turn `Thread.sleep` into virtual clock advancement.

## 5. Setting Up a Spring Boot Project with Reactor Test

The example below uses **Java 17, Maven, Spring Boot 3.5.0, and Reactor versions managed by the Spring Boot BOM**. `reactor-test` is declared directly in test scope for `StepVerifier`; do not assume the test starter supplies it implicitly.

### 5.1. File Structure

```text
reactive-virtual-time/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/virtualtime/
    │       ├── VirtualTimeApplication.java
    │       ├── ReactiveTimingService.java
    │       └── TimingController.java
    └── test/
        └── java/com/example/virtualtime/
            ├── ReactiveTimingServiceTest.java
            └── TimingControllerTest.java
```

Each public class is placed in a matching file inside package `com.example.virtualtime`. This project uses no databases, external APIs, or secrets.

### 5.2. `pom.xml`

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
    <groupId>com.example</groupId>
    <artifactId>reactive-virtual-time</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

- `spring-boot-starter-webflux` provides Reactor Core, WebFlux, and reactive HTTP handling.
- `spring-boot-starter-test` provides JUnit Jupiter, Mockito, and Spring Test.
- `reactor-test` provides `StepVerifier`, `TestPublisher`, `VirtualTimeScheduler`, and reactive test utilities.
- Do not pin a manual Reactor version here: let Spring Boot 3.5.0 dependency management select a compatible set.

`@SpringBootTest` is not needed to test a pure reactive service. Unit tests calling `new ReactiveTimingService()` suffice and avoid booting the application context. When verifying HTTP controller wiring, use an isolated `@WebFluxTest` as shown in Section 8.

## 6. Production Code with Delay, Timeout, and Retry

### 6.1. Application Entrypoint

```java
// src/main/java/com/example/virtualtime/VirtualTimeApplication.java
package com.example.virtualtime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class VirtualTimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(VirtualTimeApplication.class, args);
    }
}
```

### 6.2. `ReactiveTimingService.java`

```java
// src/main/java/com/example/virtualtime/ReactiveTimingService.java
package com.example.virtualtime;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.function.Supplier;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

@Service
public class ReactiveTimingService {

    public Mono<String> delayedGreeting(Duration delay) {
        return Mono.just("ready").delayElement(delay);
    }

    public Flux<Long> ticks(Duration interval, long count) {
        return Flux.interval(interval).take(count);
    }

    public Mono<String> simulatedRemote(Duration latency) {
        return Mono.delay(latency).thenReturn("remote-ok");
    }

    public Mono<String> withTimeout(
            Duration latency, Duration limit) {
        return simulatedRemote(latency).timeout(limit);
    }

    public Mono<String> withFallback(
            Duration latency, Duration limit) {
        return withTimeout(latency, limit)
                .onErrorResume(TimeoutException.class,
                        ignored -> Mono.just("cached"));
    }

    public Mono<String> retryTransient(
            Supplier<Mono<String>> attempt) {
        return Mono.defer(attempt)
                .retryWhen(
                        Retry.fixedDelay(2, Duration.ofSeconds(10))
                                .filter(IllegalStateException.class::isInstance)
                                .jitter(0.0)
                                .onRetryExhaustedThrow(
                                        (spec, signal) -> signal.failure()));
    }
}
```

Intentional design choices:

- `delayedGreeting` delays an existing value.
- `ticks` uses `Flux.interval`; the first element is `0L` after one full `interval`, followed by `1L`, `2L`, etc.
- `simulatedRemote` simulates a remote call using a **Reactor timer**, without performing HTTP. Therefore it **works with virtual time**.
- `withTimeout` fails with `TimeoutException` if the simulated remote takes longer than `limit`.
- `withFallback` converts only **timeouts** into `"cached"`. Other errors are not swallowed by an overly broad `onErrorResume`.
- `retryTransient` performs up to **2 retries after the initial attempt**, with a fixed **10-virtual-second** gap. It retries only on `IllegalStateException`; `IllegalArgumentException` is not retried.
- `Retry.fixedDelay` defines a retry policy; `jitter(0.0)` expresses deterministic timing for the test. With `Retry.backoff`, default jitter or growing delays must be controlled to establish an expected timeline.
- `onRetryExhaustedThrow((spec, signal) -> signal.failure())` re-emits the original failure from the final attempt when the budget runs out, letting tests expect `IllegalStateException` instead of Reactor's default retry-exhausted wrapper. That is **this example's policy**, not the default behavior of every `retryWhen`.
- `Mono.defer(attempt)` ensures the `Supplier` is called **each time upstream is subscribed**, which is essential for simulating changing outcomes across retries.

**Contract note:** in real applications, do not blindly retry every `IllegalStateException`; which exceptions are transient, how long to wait, how many retries to allow, and idempotency belong to business/operational policy. This example teaches the mechanism.

### 6.3. Reactive HTTP Controller Integrating the Service with Spring Boot

```java
// src/main/java/com/example/virtualtime/TimingController.java
package com.example.virtualtime;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class TimingController {
    private final ReactiveTimingService service;

    public TimingController(ReactiveTimingService service) {
        this.service = service;
    }

    @GetMapping(value = "/api/timing/ready",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> ready() {
        return service.delayedGreeting(Duration.ofSeconds(1));
    }
}
```

When running the application normally, `/api/timing/ready` responds with `ready` **after one real second** under healthy conditions. Only unit tests using the virtual scheduler fast-forward that second; returning a `Mono` does not make WebFlux automatically run on virtual time.

## 7. Complete Test Suite Using `StepVerifier.withVirtualTime`

The file below contains **8 `@Test` methods**. It runs with JUnit Jupiter and Reactor Test without starting a Spring context.

```java
// src/test/java/com/example/virtualtime/ReactiveTimingServiceTest.java
package com.example.virtualtime;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReactiveTimingServiceTest {

    private final ReactiveTimingService service =
            new ReactiveTimingService();

    @Test
    void delayedValueDoesNotArriveEarly() {
        StepVerifier.withVirtualTime(
                        () -> service.delayedGreeting(
                                Duration.ofHours(6)))
                .expectSubscription()
                .expectNoEvent(Duration.ofHours(5))
                .thenAwait(Duration.ofHours(1))
                .expectNext("ready")
                .verifyComplete();
    }

    @Test
    void intervalEmitsThreeItemsAtTwoSecondCadence() {
        StepVerifier.withVirtualTime(
                        () -> service.ticks(
                                Duration.ofSeconds(2), 3))
                .expectSubscription()
                .expectNoEvent(Duration.ofSeconds(1))
                .thenAwait(Duration.ofSeconds(1))
                .expectNext(0L)
                .thenAwait(Duration.ofSeconds(2))
                .expectNext(1L)
                .thenAwait(Duration.ofSeconds(2))
                .expectNext(2L)
                .verifyComplete();
    }

    @Test
    void slowRemoteFailsAtTimeoutBoundary() {
        StepVerifier.withVirtualTime(
                        () -> service.withTimeout(
                                Duration.ofSeconds(20),
                                Duration.ofSeconds(5)))
                .expectSubscription()
                .expectNoEvent(Duration.ofSeconds(4))
                .thenAwait(Duration.ofSeconds(1))
                .expectError(TimeoutException.class)
                .verify();
    }

    @Test
    void fastRemoteFinishesBeforeTimeout() {
        StepVerifier.withVirtualTime(
                        () -> service.withTimeout(
                                Duration.ofSeconds(3),
                                Duration.ofSeconds(5)))
                .expectSubscription()
                .expectNoEvent(Duration.ofSeconds(2))
                .thenAwait(Duration.ofSeconds(1))
                .expectNext("remote-ok")
                .verifyComplete();
    }

    @Test
    void timeoutCanBecomeExplicitFallback() {
        StepVerifier.withVirtualTime(
                        () -> service.withFallback(
                                Duration.ofSeconds(20),
                                Duration.ofSeconds(5)))
                .expectSubscription()
                .expectNoEvent(Duration.ofSeconds(4))
                .thenAwait(Duration.ofSeconds(1))
                .expectNext("cached")
                .verifyComplete();
    }

    @Test
    void transientErrorsAreRetriedOnVirtualSchedule() {
        AtomicInteger attempts = new AtomicInteger();

        StepVerifier.withVirtualTime(
                        () -> service.retryTransient(() -> {
                            int n = attempts.incrementAndGet();
                            return n < 3
                                    ? Mono.error(new IllegalStateException(
                                            "temporary"))
                                    : Mono.just("recovered");
                        }))
                .expectSubscription()
                .then(() -> assertEquals(1, attempts.get()))
                .expectNoEvent(Duration.ofSeconds(9))
                .then(() -> assertEquals(1, attempts.get()))
                .thenAwait(Duration.ofSeconds(1))
                .then(() -> assertEquals(2, attempts.get()))
                .expectNoEvent(Duration.ofSeconds(9))
                .thenAwait(Duration.ofSeconds(1))
                .expectNext("recovered")
                .verifyComplete();

        assertEquals(3, attempts.get());
    }

    @Test
    void nonTransientErrorIsNotRetried() {
        AtomicInteger attempts = new AtomicInteger();

        StepVerifier.withVirtualTime(
                        () -> service.retryTransient(() -> {
                            attempts.incrementAndGet();
                            return Mono.error(new IllegalArgumentException(
                                    "invalid-input"));
                        }))
                .expectSubscription()
                .expectErrorMatches(error ->
                        error instanceof IllegalArgumentException
                        && "invalid-input".equals(error.getMessage()))
                .verify();

        assertEquals(1, attempts.get());
    }

    @Test
    void retryBudgetStopsAfterThirdTotalAttempt() {
        AtomicInteger attempts = new AtomicInteger();

        StepVerifier.withVirtualTime(
                        () -> service.retryTransient(() -> {
                            attempts.incrementAndGet();
                            return Mono.error(new IllegalStateException(
                                    "unavailable"));
                        }))
                .expectSubscription()
                .expectNoEvent(Duration.ofSeconds(9))
                .thenAwait(Duration.ofSeconds(1))
                .expectNoEvent(Duration.ofSeconds(9))
                .thenAwait(Duration.ofSeconds(1))
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                        && "unavailable".equals(error.getMessage()))
                .verify();

        assertEquals(3, attempts.get());
    }
}
```

### 7.1. Timeline Comparison Across Tests

| Test | Input | Significant Virtual Timestamps | Expected |
| --- | --- | --- | --- |
| `delayedValueDoesNotArriveEarly` | `delayElement(6h)` | Silent 0→5h; advance 1h | `onNext("ready")` then complete |
| `intervalEmitsThreeItemsAtTwoSecondCadence` | `interval(2s).take(3)` | 2s, 4s, 6s | `0L`, `1L`, `2L` then complete |
| `slowRemoteFailsAtTimeoutBoundary` | latency 20s, timeout 5s | No signal through 4s; expires at 5s | `TimeoutException` |
| `fastRemoteFinishesBeforeTimeout` | latency 3s, timeout 5s | 3s | `"remote-ok"` then complete |
| `timeoutCanBecomeExplicitFallback` | latency 20s, timeout 5s | 5s | `"cached"` then complete |
| `transientErrorsAreRetriedOnVirtualSchedule` | Two errors, then success | Attempt 1 at 0s, attempt 2 at 10s, attempt 3 at 20s | `"recovered"`, 3 total attempts |
| `nonTransientErrorIsNotRetried` | `IllegalArgumentException` | Errors immediately on first try | Original error, 1 total attempt |
| `retryBudgetStopsAfterThirdTotalAttempt` | Every attempt fails transiently | 0s, 10s, 20s | Errors after 3 attempts |

In the two retry tests, `AtomicInteger` counts how many times the **`Supplier` was actually invoked**, rather than counting mock callbacks. This proves attempts 2 and 3 only happen after the virtual clock advances the full delay.

### 7.2. Why Is `Thread.sleep` Absent from All Tests?

Every delay in the sample production code is expressed via **Reactor operators**. Thanks to `withVirtualTime`, durations like 6 hours or 20 seconds are simulated. Tests do not wait for corresponding real time.

This does not guarantee **zero wall-clock time**: class loading, Maven/Spring test bootstrapping, JIT, and CPU work still consume real time. However, `Duration` delays no longer force CI to sleep for long periods.

### 7.3. What Bugs Does Checking "Silence Before the Mark" Catch?

If a developer changes `Duration.ofHours(6)` to a shorter duration, the 5-hour silence test will fail because `onNext` arrives too early. If the test had only called `thenAwait(6h)` followed by `expectNext("ready")`, it could still pass even though the code emitted at hour 2.

Similarly, when testing retries, if someone accidentally cuts the delay from 10 seconds to 2 seconds, `expectNoEvent(9s)` catches the premature retry/emission in observable cases; combined with assertions on `attempts`, you govern **retry attempt timing**, not merely the terminal result.

## 8. Testing an HTTP Controller with `@WebFluxTest` Is Not a Virtual-Time Test

To verify routing and serialization separately, use a WebFlux slice test. The service is mocked so there is no real delay, and the test client needs no virtual scheduler.

```java
// src/test/java/com/example/virtualtime/TimingControllerTest.java
package com.example.virtualtime;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebFluxTest(TimingController.class)
class TimingControllerTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    ReactiveTimingService service;

    @Test
    void endpointReturnsReactiveBodyFromService() {
        when(service.delayedGreeting(Duration.ofSeconds(1)))
                .thenReturn(Mono.just("ready"));

        client.get()
                .uri("/api/timing/ready")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("ready");

        verify(service).delayedGreeting(Duration.ofSeconds(1));
    }
}
```

**This test verifies:** the `GET /api/timing/ready` route, HTTP 200, and the response body produced from the mocked service's reactive publisher. It **does not verify** the real 1-second timer in the real service, because the service is a `@MockitoBean`.

**The tests in Section 7 verify:** the real timing, retry, and timeout logic inside the service without loading the Spring web context.

**To test a real HTTP server:** use `@SpringBootTest(webEnvironment=RANDOM_PORT)` + `WebTestClient` or an HTTP client over loopback, controlling real durations and resources; never assume virtual time in a unit test proves the entire server/network pipeline.

### 8.1. Can `@WebFluxTest` Be Combined with `withVirtualTime`?

Do not assume a test client or controller uses a scheduler controllable by `StepVerifier.withVirtualTime`. HTTP bindings, request subscriptions, Netty schedulers, Reactor context, and lifecycles may be initialized **before** the virtual scheduler is enabled.

When the goal is **operator timers**, test the service directly with Reactor Test. When the goal is the **HTTP contract**, mock the service to return `Mono.just(...)` immediately or use bounded, deterministic test fixtures. When an integration test truly needs time control, inject `Scheduler`/`Clock` cleanly and initialize contexts in an isolated lifecycle rather than mutating shared global schedulers across parallel tests.

## 9. Timeout: Understanding Operator Position and Deadlines

### 9.1. `timeout(Duration)` Is the Wait Window for an Upstream Signal

In the example:

```java
return simulatedRemote(Duration.ofSeconds(20))
        .timeout(Duration.ofSeconds(5));
```

Upstream emits nothing within 5 virtual seconds. `timeout` emits `TimeoutException` downstream and cancels the unresponsive source's subscription. **It does not mean a real remote call was aborted at the network layer** if your client does not honor cancellation.

For `Flux`, `timeout(Duration)` typically measures the gap between signals rather than a total stream deadline. If `Flux.interval(2s)` keeps emitting items before the `5s` limit, each emitted item resets the timer waiting for the next signal. If a workflow requires a 5-second total wall-clock budget, use a different policy (such as racing against an overall timer or scoping the timeout explicitly across the whole sequence).

### 9.2. Are Timeout and Fallback a Success?

`onErrorResume(TimeoutException.class, ignored -> Mono.just("cached"))` turns a timeout error into **an alternative successful output**. Tests must verify the exact business meaning:

- Fall back **only** on `TimeoutException`, without swallowing every exception.
- Fallback is not proof that upstream succeeded.
- If consumers must distinguish stale/cached data, the contract should carry metadata in the response rather than returning a string identical to live data.
- On timeout, you may also need to check cancellation, metrics, circuit-breaker state, or distinguish timeouts from permanent failures.

Do not write only `expectNextCount(1).verifyComplete()` for a fallback: a wrong value would still pass. Assert `expectNext("cached")` and any key side effects.

### 9.3. Timeout Before Retry or Retry Before Timeout?

Two expressions behave fundamentally differently:

```java
// PATTERN A: timeout applies to each individual attempt.
Mono<String> a = source.timeout(Duration.ofSeconds(3))
        .retryWhen(retrySpec);

// PATTERN B: timeout applies to the entire chain after retries.
Mono<String> b = source.retryWhen(retrySpec)
        .timeout(Duration.ofSeconds(3));
```

**These are two illustrative snippets**: `source` and `retrySpec` are hypothetical variables, not standalone classes from Section 6.

- A: an attempt exceeding 3 seconds → timeout error → the retry policy **may** retry if its filter permits `TimeoutException`. Total time across all attempts and backoffs can exceed 3 seconds.
- B: the 3-second deadline spans the initial attempt, retries, and backoff delays within the downstream subscription; on expiration, the entire workflow fails and pending retries can be cancelled.
- If the retry filter only allows `IllegalStateException` as in the sample project, `TimeoutException` in A will **not** be retried.

Write tests for the **exact operator placement** you chose. Do not equate `timeout` with an HTTP client network timeout: connect timeout, response timeout, TCP retries, and Reactor signal timeouts are separate mechanisms.

### 9.4. Be Careful with Exact Equal Boundary Timestamps

When an event and a timeout are scheduled for the exact same timestamp `t=5s`, same-timestamp execution order can affect outcomes in some pipelines. Tests should pick clear cases:

- Fast: latency **3s**, timeout **5s** → must succeed.
- Slow: latency **20s**, timeout **5s** → must fail with `TimeoutException`.
- The boundary case of latency **5s** and timeout **5s** must be settled by the contract and specific scheduler semantics before asserting.

Avoid drawing strong conclusions about implementation correctness from ambiguous boundary ties where two signals share the exact same timestamp.

## 10. Retry: Timing, Attempt Counts, and Error Types

### 10.1. `retry(2)` vs. `retryWhen(Retry.fixedDelay(2, ...))`

`retry(2)` permits up to two resubscriptions on error, typically with no delay between retries. `Retry.fixedDelay(2, Duration.ofSeconds(10))` inserts a 10-second pause between retries and supports filtering error types.

**Do not confuse `maxRetries=2` with 2 total calls.**

```text
t = 0s       attempt #1  → IllegalStateException
t = 10s      attempt #2  → IllegalStateException
t = 20s      attempt #3  → "recovered"  → onComplete

Total calls = 1 initial attempt + 2 retries = 3.
Backoff delays elapsed = 2.
```

If retries never succeed and the budget is exhausted, the sample production code uses `onRetryExhaustedThrow` to re-emit the last error. Without that custom policy, Reactor emits a "retry exhausted" wrapper error whose cause is the prior failure. When changing retry policies, update expected error types accordingly.

### 10.2. Why Does `Mono.defer` Matter?

Incorrect:

```java
int n = attempts.incrementAndGet();
Mono<String> source = n < 3
        ? Mono.error(new IllegalStateException("unavailable"))
        : Mono.just("ok");

return source.retryWhen(Retry.fixedDelay(
        2, Duration.ofSeconds(10)));
```

This is an illustrative anti-pattern: `n` increments **only once at assembly time**. `retryWhen` resubscribes to the **exact same failing publisher**, so the business attempt counter never advances and the source keeps failing.

Correct when you want a fresh attempt per subscription:

```java
return Mono.defer(() -> {
    int n = attempts.incrementAndGet();
    return n < 3
            ? Mono.error(new IllegalStateException("temporary"))
            : Mono.just("ok");
}).retryWhen(Retry.fixedDelay(
        2, Duration.ofSeconds(10)));
```

These snippets illustrate the pattern; in the main project `ReactiveTimingService#retryTransient` already wraps `Supplier<Mono<String>>` in `Mono.defer(attempt)`.

**Note:** `retryWhen` works via resubscription. For hot publishers, one-way message streams, or side effects that already occurred, resubscribing **does not** guarantee re-running business work like a fresh HTTP request. Understand cold/hot semantics, idempotency, and repeatability.

### 10.3. Filtering Errors and Avoiding Unconditional Retries

For user input validation:

- `IllegalArgumentException` is a permanent error in this example; retrying cannot fix bad input and brings no benefit.
- `IllegalStateException` is used as a transient marker **for teaching purposes only**; in production, define an explicit domain exception (e.g., `TransientGatewayException`).
- `TimeoutException` may or may not be retried depending on SLA, request idempotency, side effects, and overall deadline.
- HTTP 429/503 responses are not automatically safe to retry for every method, especially payment `POST` calls lacking an idempotency key.

`nonTransientErrorIsNotRetried` checks **only 1 attempt**; `retryBudgetStopsAfterThirdTotalAttempt` checks failure **after exactly 3 attempts**. Both catch policy mistakes beyond output assertions alone.

### 10.4. `Retry.backoff` and Jitter

`Retry.backoff(maxRetries, initialDelay)` increases delays exponentially and applies jitter to prevent retry storms. While valuable in production, jitter makes exact timelines unpredictable if tests assert exact second-by-second boundaries. When testing **deterministic timelines**:

- Use `Retry.fixedDelay` for fixed-delay contracts.
- For `Retry.backoff`, disable jitter via `jitter(0.0)` or assert within appropriate windows/ranges rather than asserting a fixed random sequence.
- Test "exactly 2 retries" separately from "delay/backoff policy" when useful.
- If a retry policy includes `maxBackoff`, pre-retry hooks, or retry filters, reflect those conditions in expectations.

**Do not set jitter = 0 in production just to pass tests** when jitter is needed to shed load spikes. Retry configuration should be testable with fake policies or controlled schedulers while preserving the designed production policy.

## 11. How to Test Cancellation on Timeout?

After `timeout`, the upstream subscription is cancelled. To prove the service stops waiting and tears down the subscription, use `doOnCancel` or `doFinally` at the right operator position.

Example test method **you can add** to `ReactiveTimingServiceTest` in Section 7 (import `AtomicBoolean` and `assertTrue` if added):

```java
@Test
void timeoutCancelsSlowPublisher() {
    AtomicBoolean cancelled = new AtomicBoolean();

    StepVerifier.withVirtualTime(() ->
                    Mono.delay(Duration.ofSeconds(30))
                            .doOnCancel(
                                    () -> cancelled.set(true))
                            .thenReturn("never")
                            .timeout(Duration.ofSeconds(5)))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(5))
            .expectError(TimeoutException.class)
            .verify();

    assertTrue(cancelled.get());
}
```

**Limitation:** cancellation is observed on the Reactor subscription, which does not prove an HTTP request stopped running on a remote server. When non-cancellable side effects exist, add idempotency/circuit breakers, resource cleanup, or integration tests.

With `doFinally`, `SignalType.CANCEL` can appear at different points depending on operator placement. Do not assert a downstream operator's callback and assume it reflects upstream cancellation. Place the hook directly on the publisher you intend to observe.

## 12. Using `VirtualTimeScheduler` Directly When Fine Clock Control Is Needed

`StepVerifier.withVirtualTime` is usually the simplest option because it manages the virtual scheduler around the scenario. When testing an explicit scheduler instance, Reactor Test also provides `VirtualTimeScheduler`.

Example **independent of the project in Section 7**:

```java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.test.scheduler.VirtualTimeScheduler;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ManualVirtualClockTest {

    @Test
    void runsScheduledTaskWithoutWaitingForWallClock() {
        VirtualTimeScheduler clock = VirtualTimeScheduler.create();
        AtomicInteger executed = new AtomicInteger();

        clock.schedule(
                executed::incrementAndGet,
                30,
                java.util.concurrent.TimeUnit.SECONDS);

        assertEquals(0, executed.get());

        clock.advanceTimeBy(Duration.ofSeconds(29));
        assertEquals(0, executed.get());

        clock.advanceTimeBy(Duration.ofSeconds(1));
        assertEquals(1, executed.get());

        clock.dispose();
    }
}
```

This is an **extra test class**, not in the Section 5 file tree unless you create `ManualVirtualClockTest.java`. It demonstrates scheduling a task on the virtual scheduler directly, not Reactor `Mono`/`Flux` automatically picking up this clock.

**Critical distinction:** calling `VirtualTimeScheduler.create()` does **not automatically** make every `Schedulers.parallel()` in the app use that scheduler. For operators to use a specific clock directly, inject the scheduler; or use `withVirtualTime`, which replaces default factories for the test. If you install a global factory or call `VirtualTimeScheduler.getOrSet()`, manage cleanup/reset carefully to avoid affecting other tests.

### 12.1. When Is Injecting a `Scheduler` Beneficial?

Suppose a production class accepts a `Scheduler` through its constructor:

```java
public final class DelayedCommand {
    private final Scheduler scheduler;

    public DelayedCommand(Scheduler scheduler) {
        this.scheduler = scheduler;
    }

    public Mono<String> run() {
        return Mono.delay(
                Duration.ofMinutes(10), scheduler)
                .thenReturn("done");
    }
}
```

This is an **illustrative snippet** needing `Scheduler`, `Mono`, and `Duration` imports. Tests can create `VirtualTimeScheduler clock = VirtualTimeScheduler.create()`, inject it, and verify the stream with `StepVerifier.create` alongside `clock.advanceTimeBy` at the right steps. That design avoids relying on global scheduler factories when the app uses dedicated schedulers.

Never mix an injected scheduler with `StepVerifier.withVirtualTime` assuming both share one clock. If an operator uses an explicit custom scheduler, the test must advance **that exact scheduler**.

## 13. Distinguishing `verify()` from Real Test Deadlines

Many tests hang because they forget to advance the virtual clock. When that happens, `verifyComplete()` waits for a terminal signal that never arrives. Add a watchdog guard:

```java
StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(10))
                        .thenReturn("ok"))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(10))
        .expectNext("ok")
        .expectComplete()
        .verify(Duration.ofSeconds(5));
```

Here:

- `thenAwait(10s)` advances **10 virtual seconds**.
- `verify(Duration.ofSeconds(5))` sets a **real-time limit** so verification cannot hang indefinitely.
- `verify()`/`verifyComplete()` executes the test; constructing a builder without calling verify proves nothing.
- The `Duration` returned by `verify()` is the real elapsed time taken to run verification, not the virtual duration simulated by the pipeline.

**Do not set the watchdog so low that busy Maven/CI machines fail spuriously.** It is a hang-detection safeguard, not a business deadline assertion.

If code uses `StepVerifier.setDefaultTimeout(...)`, that global configuration affects subsequent verifiers and must be reset after the test. To minimize cross-test interaction, prefer per-scenario `verify(Duration)` wherever possible.

## 14. Common Mistakes That Make Virtual Time "Stop Working"

### Mistake 1: Publisher Created Before `withVirtualTime`

**Symptom:** Test runs in real time, emits nothing, or hangs.  
**Cause:** Timed publisher/operator captured a real scheduler before the virtual scheduler was enabled.  
**Fix:** Build the entire pipeline inside the `Supplier`; if a bean constructs and stores a publisher in its constructor, refactor to create it on method call/subscribe or inject a scheduler.

### Mistake 2: `expectNoEvent` Is the First Step

**Symptom:** Assertion fails immediately upon subscription.  
**Cause:** Subscription counts as an event.  
**Fix:** `expectSubscription().expectNoEvent(...)`.

### Mistake 3: `expectNext` Comes Before Advancing Time

**Symptom:** Test waits forever for an element scheduled in the future.  
**Cause:** Virtual clock is still at `t=0`, while the element is scheduled for `t=10s`.  
**Fix:** Call `thenAwait(Duration.ofSeconds(10))` or `expectNoEvent` appropriately before expecting the next signal.

### Mistake 4: Using `Thread.sleep` or Blocking I/O

**Symptom:** Test still takes many seconds or times out in CI.  
**Cause:** Wall-clock/blocking operations are not Reactor-scheduled timers.  
**Fix:** Replace upstream with a deterministic fake `Mono`/`Flux` or inject `Clock`/`Scheduler`; keep network integration tests separate.

### Mistake 5: Retry Repeats the Same Result Across Subscriptions

**Symptom:** Retried twice yet got the exact same error every time; attempt counter stayed flat.  
**Cause:** Counter/request executed at assembly time, not inside `Mono.defer`.  
**Fix:** Wrap attempt creation in a `Supplier` invoked per subscription. For real HTTP operations, also verify idempotency.

### Mistake 6: Miscounting Retry Attempts

**Symptom:** Test thinks `Retry.fixedDelay(2, ...)` calls upstream only 2 times.  
**Cause:** Parameter `2` is the number of **retries**, excluding the initial attempt.  
**Fix:** Assert **3 total attempts** and two backoff delays when the source continues failing.

### Mistake 7: Custom Scheduler Is Not Under the Virtual Clock

**Symptom:** `thenAwait` does not trigger scheduled tasks.  
**Cause:** Operator uses a scheduler created before the lambda or a custom scheduler.  
**Fix:** Create publishers lazily, inject/advance the exact scheduler, and avoid creating `Schedulers.newSingle` outside test ownership.

### Mistake 8: Jitter Makes the Timeline Non-Deterministic

**Symptom:** Retry test passes sometimes and fails other times with `Retry.backoff`.  
**Cause:** Retry delays vary due to jitter/policy.  
**Fix:** Test deterministic timing with `jitter(0)` when appropriate, or assert within valid ranges matching the real policy—never remove production jitter solely for tests.

### Mistake 9: Using a Hot Publisher in a Retry Test

**Symptom:** Retries do not re-run work, lose signals, or depend on subscription timing.  
**Cause:** Hot sources share signals rather than re-running per subscription.  
**Fix:** Use cold publishers/`Mono.defer` for per-attempt behavior; if testing a hot stream, test its multicast/subscription semantics properly.

### Mistake 10: Virtual-Time Tests Running in Parallel with Other Scheduler-Mutating Tests

**Symptom:** Flakiness due to shared scheduler state.  
**Cause:** `withVirtualTime` swaps shared scheduler factories per Reactor Test mechanics.  
**Fix:** Do not run multiple global-scheduler-mutating tests in parallel without isolation; prefer injected `Scheduler` instances, avoid static timer publishers in test classes, and reset custom hooks after tests.

### Mistake 11: Checking Only Final Output While Ignoring Deadlines

**Symptom:** Test stays green even when responses arrive early or retries happen too fast.  
**Cause:** Only calling `thenAwait` and `expectNext` without asserting quiet windows or attempt counts.  
**Fix:** Combine `expectNoEvent`, `AtomicInteger`, and checks before/after deadlines.

### Mistake 12: Treating `WebTestClient` as If It Fast-Forwards Time

**Symptom:** WebFlux slice/integration tests still wait in real time.  
**Cause:** `WebTestClient` is an HTTP test client, not `VirtualTimeScheduler`.  
**Fix:** Test timed operators at the service layer with `StepVerifier.withVirtualTime`; test HTTP mapping separately with stubs/immediate responses.

### Mistake 13: Confusing the `timeout` Operator with HTTP Connection Timeouts

**Symptom:** Unit timeout test passes, yet production sockets still hang.  
**Cause:** Reactive signal timeouts do not necessarily govern HTTP transport connect/read timeouts or remote side effects.  
**Fix:** Configure HTTP client/broker timeouts separately, verify cancellation, and run integration/staging network timeout tests.

### Mistake 14: Forgetting the Terminal Assertion

**Symptom:** Checked `onNext` without verifying whether the stream completed or errored afterward.  
**Cause:** Missing terminal signal verification.  
**Fix:** Append `verifyComplete`, `expectError(...).verify()`, or `thenCancel().verify()` per contract.

## 15. Advanced Testing: Demand and Clock Synchronization

### 15.1. Backpressure with `Flux.interval`

`Flux.interval` emits on clock ticks. If a subscriber has not requested enough demand when the next tick arrives, an overflow error or unexpected behavior can occur. The `StepVerifier.withVirtualTime(() -> publisher)` overload defaults to unbounded demand, keeping Section 7's examples focused on timing.

When genuinely testing `request(n)`/backpressure, use `withVirtualTime(supplier, initialRequest)` or `StepVerifierOptions`, calling `thenRequest(n)` at the right moments. Assert behavior when a tick fires at zero demand rather than extrapolating from unbounded tests.

### 15.2. `flatMap` Nesting Timed Publishers

Example:

```java
Flux.just("A", "B")
        .flatMap(value ->
                Mono.delay(Duration.ofSeconds(3))
                        .thenReturn(value));
```

This is an illustrative snippet. With `flatMap`, inner publishers are created when upstream emits items; **if the virtual clock advances before inner publishers are created/subscribed**, the timeline shifts away from naive expectations. Trace the subscription/scheduling order, step through time incrementally, and place `thenAwait`/`expectNoEvent` between stages. With `concatMap`, inner sources run sequentially, shifting deadlines further.

**Important:** never assume "advancing 3 seconds guarantees every inner `Mono.delay(3s)` finished". Inner timers may start after an earlier advance. Lazy outer creation is necessary but not sufficient; the exact moment inner streams subscribe also matters.

### 15.3. `PublisherProbe` and `TestPublisher`

`reactor-test` also offers:

- **`PublisherProbe`:** tracks whether a reactive publisher was subscribed/requested/cancelled, useful for testing fallback branches or `switchIfEmpty`.
- **`TestPublisher`:** programmatically emits `onNext`, `onComplete`, and `onError` to test operator/downstream behavior.

Neither replaces the virtual clock. They control **signals**, while `VirtualTimeScheduler` controls **scheduling time**. Complex tests can combine both, taking care to avoid races from uncontrolled cross-thread signal emissions.

### 15.4. Should Retries with Side Effects Test Idempotency?

Yes. `retryWhen` can re-execute network requests or write operations after failures. If an error occurs **after the remote side effect already succeeded**, careless retries can duplicate orders, charges, or messages. Virtual time only proves the retry schedule and budget; it does not prove side effects are idempotent.

For payments and orders, enforce idempotency keys, duplicate detection, transactional semantics, and integration tests at real boundaries. Never treat a virtual-time test as proof that a retry policy is production-safe.

## 16. Practice Exercises

### Exercise 1: Prevent Emission Before the 24-Hour Mark

Write `Mono.delay(Duration.ofDays(1)).thenReturn("expired")`. Test with `withVirtualTime`:

- After subscribing, zero events for 23 hours.
- Advance 1 more hour.
- Emit `"expired"` and complete.

**Hint:** `expectSubscription().expectNoEvent(Duration.ofHours(23)).thenAwait(Duration.ofHours(1))...`.

### Exercise 2: Total Timeout vs. Per-Attempt Timeout

Simulate a source always taking 4 seconds with up to two retries. Try placing `timeout(3s)` both before and after retry. Write expectations for each case with a retry filter permitting `TimeoutException`, observing resubscription counts in virtual time.

**Criterion:** show why a 3-second total deadline differs from a 3-second deadline **per attempt** plus backoffs.

### Exercise 3: Business Errors Must Not Retry

Write a source returning `Mono.error(new IllegalArgumentException("bad"))`. Verify:

- `expectError(IllegalArgumentException.class)`.
- Attempt count equals 1.
- No delay/backoff precedes the terminal error.

**Hint:** increment `AtomicInteger` inside the `Supplier`, not before pipeline assembly.

### Exercise 4: Two Transient Failures Then Success

Configure `Retry.fixedDelay(2, 10s)` with a `Supplier` failing on attempts 1 and 2 and returning `"ok"` on attempt 3. Verify:

- Attempt 1 at `t=0`.
- No retry before `t=10s`.
- Attempt 2 at `t=10s`.
- Attempt 3 at `t=20s`.
- Emits `"ok"` and completes.

**Reference solution:** `transientErrorsAreRetriedOnVirtualSchedule` in Section 7.

### Exercise 5: Pre-Built Publisher

Write a test intentionally creating `Mono.delay(1h)` before `withVirtualTime` and observe why its behavior should not be trusted. Fix it by moving publisher construction into the lambda, and add a real watchdog timeout so the test never hangs.

**Note:** this exercise teaches recognizing an anti-pattern. Do not leave an intentionally broken test running unbounded in main CI.

## 17. Checklist Before Reviewing a Reactive Timing Test

- [ ] Uses `reactor-test` and `StepVerifier.withVirtualTime` for compatible time operators.
- [ ] Publishers and timed operators are **created inside the `Supplier`** passed to the verifier.
- [ ] No static/cached publishers initialized schedulers before virtual time was activated.
- [ ] `expectSubscription` appears before `expectNoEvent`.
- [ ] Uses `expectNoEvent` when the contract forbids early signals.
- [ ] Uses `thenAwait` when advancing the clock so operators emit signals.
- [ ] Asserts exact values/errors/completions, not just `expectNextCount` or retry counts.
- [ ] Distinguishes real-time `verify(Duration)` watchdogs from virtual delays.
- [ ] Retry tests count **initial attempt + retries**, without misreading `maxRetries`.
- [ ] Tests both **non-retried error types** and the retry-exhausted path.
- [ ] Backoff jitter and time windows are controlled when asserting deterministic timelines.
- [ ] Virtual-time tests do not trigger real production networks, databases, or side effects.
- [ ] Does not expect virtual time to speed up `Thread.sleep` or network I/O.
- [ ] For hot/async/`flatMap` sources, accounts for inner subscription timing and real schedulers.
- [ ] Does not corrupt global scheduler factories during parallel test execution.
- [ ] Uses Reactor unit tests for timers and WebFlux slice/integration tests for HTTP contracts.

## 18. Self-Check Questions

**Question 1.** Why does `withVirtualTime` require `Supplier<Publisher<?>>` instead of a pre-built publisher?

**Answer:** It must install the virtual scheduler before timed operators are constructed; pre-building risks capturing a real scheduler outside virtual-time control.

**Question 2.** How does `expectNoEvent(5s)` differ from `thenAwait(5s)`?

**Answer:** Both advance the clock in virtual tests; `expectNoEvent` also fails if any event arrives during that window, whereas `thenAwait` does not assert silence.

**Question 3.** Why is `expectSubscription()` needed before `expectNoEvent`?

**Answer:** `onSubscribe` is itself an event; expecting no events from the very beginning causes the test to fail on the valid subscription event.

**Question 4.** How many maximum attempts does `Retry.fixedDelay(2, Duration.ofSeconds(10))` execute?

**Answer:** Up to **3**: one initial attempt plus two retries, at 0s, 10s, and 20s if transient errors persist without jitter or extra latency.

**Question 5.** Does `timeout(5s)` automatically set Netty's HTTP connect timeout to 5s?

**Answer:** No. That is a reactive publisher signal timeout; network connect/read timeouts and remote cancellation require separate configuration and testing.

**Question 6.** With `Mono.delay(30s)` and `timeout(5s)`, what error does the test expect?

**Answer:** Typically `TimeoutException` at virtual `t=5s`, after `timeout` cancels the upstream subscription; if `onErrorResume` is present, it can turn into a fallback per policy.

**Question 7.** Why should retry tests use `Mono.defer` or a `Supplier` generating attempts per subscription?

**Answer:** `retryWhen` works by resubscribing; if attempt logic or counters run at assembly time, they only execute once and fail to model real retries.

**Question 8.** Does virtual time speed up `Thread.sleep(10000)` inside `Mono.fromCallable`?

**Answer:** No. `Thread.sleep` blocks for wall-clock time; use fakes or refactor to Reactor timers / injected schedulers for deterministic testing.

**Question 9.** Does a passing `@WebFluxTest` + `WebTestClient` prove a 6-hour service delay was tested?

**Answer:** No, if the service is mocked or the client runs on real schedulers. Test operator timing separately with `StepVerifier.withVirtualTime`; WebFlux tests mainly check routing and HTTP mapping.

**Question 10.** If a source succeeds at the exact timeout deadline, what should a test do?

**Answer:** Clarify policy and scheduler semantics; cover clear fast/slow cases first and add boundary tests when specified, avoiding conclusions based on assumed execution order for same-timestamp tasks.

## 19. Official References

- [Project Reactor – Testing Reactor Code / Manipulating Time](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, virtual time, lazy `Supplier`, and expectations.
- [Project Reactor – StepVerifier API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): `withVirtualTime` overloads, `thenAwait`, `expectNoEvent`, `verify`.
- [Project Reactor – VirtualTimeScheduler API](https://projectreactor.io/docs/test/release/api/reactor/test/scheduler/VirtualTimeScheduler.html): creating, advancing, and managing virtual schedulers.
- [Project Reactor – Retry API](https://projectreactor.io/docs/core/release/api/reactor/util/retry/Retry.html): `Retry.fixedDelay`, `Retry.backoff`, retry budget.
- [Project Reactor – RetryBackoffSpec API](https://projectreactor.io/docs/core/release/api/reactor/util/retry/RetryBackoffSpec.html): jitter, filter, exhaustion handling.
- [Spring Boot 3.5 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): test context, WebFlux slice, and test dependencies.

**Key takeaway:** Virtual time **does not turn the entire application into a zero-latency environment**. It only lets tests **control the clock of Reactor operators whose schedulers are swapped**. To write solid tests for `delay`, `timeout`, and `retry`, build publishers lazily, advance time deliberately, and verify **no early emission**, **correct terminal signal**, and **exact retry policy**.
