# Creating Publishers at the Right Time When Using StepVerifier.withVirtualTime

In **Spring Boot and Project Reactor**, many pipelines use **Mono.delay**, **Flux.interval**, **delayElements**, **timeout**, **retryWhen**, or other operators requiring a Scheduler. When testing against a real wall clock, a test like "wait one day" is clearly impractical. **StepVerifier.withVirtualTime** from `reactor-test` swaps the time management of Reactor-supported Schedulers with **VirtualTimeScheduler**, allowing tests to fast-forward the clock without actually waiting for hours.

However, virtual time only works when **the pipeline is created at the right time**. The single most important rule is to **provide a `Supplier<Publisher<T>>` that builds the publisher after the virtual scheduler has been activated**. If you pre-build a `Mono`/`Flux` containing a time-based operator and return it from the lambda merely to satisfy the syntax, the operator may already hold a reference to a real Scheduler: the test will wait, hang, or run in real time even if you call `thenAwait`.

This lesson explains **assembly – subscription – scheduling – verification**, right and wrong ways to write it, a runnable example with **Java 17, Spring Boot 3.4.5, Reactor Test, and JUnit Jupiter**, the limits of virtual time, and a systematic way to diagnose errors.

## 1. Why Does the Supplier Matter More Than Lambda Syntax?

Look at two seemingly equivalent ways of writing the test.

**Wrong for virtual time (do not put into a test suite):**

~~~java
Mono<Long> alreadyBuilt = Mono.delay(Duration.ofHours(12));

StepVerifier.withVirtualTime(() -> alreadyBuilt)
    .expectSubscription()
    .thenAwait(Duration.ofHours(12))
    .expectNext(0L)
    .verifyComplete();
~~~

The **alreadyBuilt** variable was constructed **before** `StepVerifier` activated the virtual scheduler. Some time-based operators resolve the Scheduler during **assembly**, for instance via `Schedulers.parallel()`. The `Supplier` here does not create a new pipeline; it just returns the old object. As a result, execution may rely on the real Scheduler or fail to advance on the virtual clock. Never try to "fix" this with `Thread.sleep` or multi-hour test timeouts.

**Correct: instantiate timed operators inside the Supplier**

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofHours(12)))
    .expectSubscription()
    .thenAwait(Duration.ofHours(12))
    .expectNext(0L)
    .verifyComplete();
~~~

When `StepVerifier` sets up the test, it installs `VirtualTimeScheduler` first and only then invokes the **`Supplier`** to obtain the Publisher. Thus **Mono.delay** and its default Scheduler are resolved within the virtual-time scope. After **thenAwait(12 virtual hours)**, the Mono emits **0L** and completes without waiting 12 real hours.

**Rule of thumb:** the publisher should be **created inside the lambda**, not **merely returned from the lambda**.

### What Does Reactor Document?

The Reactor Test API accepts **`Supplier<? extends Publisher<? extends T>>`** rather than an already-built `Publisher` because time-based operators must be instantiated after the virtual clock is enabled. The documentation warns against building a `Flux` ahead of time and having the `Supplier` return that existing variable. See the official references at the end of this lesson, especially *Manipulating Time* and the `StepVerifier` Javadoc.

This is not a variable-naming convention or lambda-bracing style; it is about **execution order of the code constructing the operator**.

## 2. Four Moments to Distinguish: Assembly, Subscription, Scheduling, Emission

| Moment | What Happens | Risk Under Virtual Time |
| --- | --- | --- |
| **Assembly** | Code calls `Mono.delay`, `Flux.interval`, `timeout`, `retryWhen`, `publishOn`, etc. to build the pipeline | A timed operator may capture the default Scheduler or an explicitly passed scheduler right now |
| **Subscription** | `StepVerifier` subscribes; Reactor creates the `Subscription` and triggers subscription logic | Some operators/`defer` only create work, register timers, or schedule tasks upon subscription |
| **Scheduling** | Operator submits a task to a `Scheduler` with a target execution time | If the scheduler is real or custom, `thenAwait` on `VirtualTimeScheduler` cannot fast-forward it |
| **Emission** | `onNext`, `onError`, `onComplete` are delivered to the subscriber | `StepVerifier` must advance the virtual clock in proper steps and supply demand to observe signals |

**A Publisher being lazy** does not mean everything inside it is resolved lazily. In Reactor, most data processing waits until subscribe time, yet **constructing an operator** can lock in a scheduler/clock or capture external references upfront. Therefore, "Reactor is lazy" **does not** justify pre-assembling pipelines before `withVirtualTime`.

Example:

~~~java
Mono<String> timeBound = Mono.delay(Duration.ofMinutes(30))
    .map(ignored -> "ready");
~~~

Although `"ready"` is only emitted on subscription, the timer source **`Mono.delay(...)`** was constructed at assembly time. If created in a Spring singleton constructor, by the time JUnit runs the test it may already hold a previously captured Scheduler.

### A Valid Pattern with a Pre-Created Service Object

**Creating the service object beforehand is allowed**, provided the service method **builds a fresh publisher each time it is called**:

~~~java
TimedStreamService service = new TimedStreamService();

StepVerifier.withVirtualTime(
        () -> service.delayed("ready", Duration.ofHours(6)))
    .expectSubscription()
    .thenAwait(Duration.ofHours(6))
    .expectNext("ready")
    .verifyComplete();
~~~

The `Supplier` invokes the service method after virtual setup; the method creates a new `Mono.delay` per call. However, if **`service.delayed(...)`** simply returns a `Mono` field stored in the constructor, the lambda will not help. Inspect the implementation, not just the method signature.

## 3. How Does `StepVerifier.withVirtualTime` Execute?

**`StepVerifier.create(publisher)`** takes an existing publisher and observes it in real time; it suits synchronous logic or very short time-based tests. **`StepVerifier.withVirtualTime(supplier)`** sets up a virtual scheduler around verification to control the default schedulers used by operators.

Key methods:

- **`expectSubscription()`**: asserts the subscribe event. Place this before `expectNoEvent`.
- **`expectNoEvent(Duration)`**: advances time while **FAILING if any event occurs** in that interval; note that **subscription** itself counts as an event.
- **`thenAwait(Duration)`**: advances time without **asserting the absence of events** during that interval. In virtual mode, it **advances the virtual clock**.
- **`expectNext(value)`**: asserts an `onNext` with the exact value.
- **`expectNextCount(n)`**: checks the `onNext` count when exact contents are not checked.
- **`expectComplete()`** and **`verifyComplete()`**: verify completion.
- **`expectError(...)`** and **`verifyError(...)`**: verify errors.
- **`thenCancel()`**: stops testing for non-terminating streams.
- **`verify(Duration.ofSeconds(5))`**: bounds the **real wall-clock time** the test is allowed to spend verifying; not the virtual duration needed by the pipeline.
- **`withVirtualTime(supplier, initialRequest)`**: controls initial demand, though you must call `thenRequest` before a timer fires, or sources like `Flux.interval` may signal overflow for lack of demand.

**Do not put `expectNoEvent` as the first step**:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofDays(1)))
    .expectNoEvent(Duration.ofHours(1))  // Wrong: subscription is an event.
    .thenAwait(Duration.ofHours(23))
    .expectNext(0L)
    .verifyComplete();
~~~

**Fix with `expectSubscription()`:**

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofDays(1)))
    .expectSubscription()
    .expectNoEvent(Duration.ofHours(23))
    .thenAwait(Duration.ofHours(1))
    .expectNext(0L)
    .verifyComplete();
~~~

The second example makes a strong assertion: **no early emission** for 23 virtual hours, followed by the exact value after 1 more virtual hour. Using only `thenAwait(1 day)` fails to directly guard the "must not emit early" requirement.

### Does `StepVerifier` Always Run Faster?

Virtual time can jump from 0 to many hours in just a few internal scheduling steps. However, real CPU work, I/O, thread locks, JDBC, networking, or `Thread.sleep` **are not magically sped up by `VirtualTimeScheduler`**. Therefore, a virtual-time test can still run slowly or hang if the pipeline relies on work outside the virtual scheduler.

Do not assert that `verify()` takes exactly 0 ms. Real speed depends on build tools, JVM, GC, and CI; assert **emission order and time contracts**, not runner microseconds.

## 4. Operators That Typically Need Creation Inside the Supplier

| Operator / Operation | Effect | Virtual Clock Scenario |
| --- | --- | --- |
| **`Mono.delay(duration)`** | Emits `0L` after the wait | Test waiting an hour or a day |
| **`Flux.interval(period)`** | Emits `0L`, `1L`, ... periodically; first after `period` | Test heartbeats or polling |
| **`delayElements(duration)`** | Delays each `onNext` | Test spacing between arriving items |
| **`timeout(duration)`** | Signals `TimeoutException` if source fails to emit in time | Test fallback/timeout logic |
| **`retryWhen(Retry.fixedDelay(...))`** | Retries after fixed backoff | Test retry counts and eventual success |
| **`retryWhen(Retry.backoff(...))`** | Exponential backoff, optionally with jitter | Requires controlling jitter and scheduling conditions |
| **`delaySubscription(duration)`** | Delays starting subscription | Must not emit/subscribe before deadline |
| **`publishOn(Schedulers.parallel())`** | Switches Scheduler for downstream processing | Scheduler must be resolved inside virtual scope to use virtual clock |
| **`subscribeOn(scheduler)`** | Schedules subscription on a given scheduler | If scheduler was created upfront, virtual time may not control it |

This list does not imply every operator captures its scheduler in the **exact same** method or Reactor version. A safer rule is to **keep the entire assembly of the timed chain inside the `Supplier`**, then confirm which scheduler the operators actually use.

Dedicated custom schedulers like **`Schedulers.newSingle("real")`**, **`Schedulers.fromExecutor(...)`**, or third-party executors **are not automatically swapped for `VirtualTimeScheduler`** merely because you use `withVirtualTime`. If an operator explicitly uses a custom scheduler outside Reactor's virtualized factory hook, `thenAwait` does not advance that scheduler's clock.

## 5. Common Counterexample: Building the Publisher in a Fixture Field

In a test class or Spring bean, developers often assemble publishers in fields:

~~~java
class FragileExample {
    // Initialized when the test instance is created, before withVirtualTime.
    private final Flux<Long> ticks =
            Flux.interval(Duration.ofMinutes(30));

    void verifyTicks() {
        StepVerifier.withVirtualTime(() -> ticks)
            .expectSubscription()
            .thenAwait(Duration.ofMinutes(30))
            .expectNext(0L)
            .verifyComplete();
    }
}
~~~

**This is a counterexample; do not run it as a standard test.** The flaw is that **`ticks`** holds a timed operator built outside the virtual-time setup. Do not try to patch it by swapping `expectNoEvent` for `thenAwait` or raising test timeouts.

**First fix — factory method creating a new Publisher:**

~~~java
class BetterExample {
    Flux<Long> ticks() {
        return Flux.interval(Duration.ofMinutes(30));
    }

    void verifyTicks() {
        StepVerifier.withVirtualTime(this::ticks)
            .expectSubscription()
            .thenAwait(Duration.ofMinutes(30))
            .expectNext(0L)
            .thenCancel()
            .verify();
    }
}
~~~

**Second fix — build directly inside the lambda:**

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofMinutes(30)).take(3))
    .expectSubscription()
    .thenAwait(Duration.ofMinutes(30))
    .expectNext(0L)
    .thenAwait(Duration.ofMinutes(30))
    .expectNext(1L)
    .thenAwait(Duration.ofMinutes(30))
    .expectNext(2L)
    .verifyComplete();
~~~

In the first fix, `Flux.interval` is **infinite**, so `thenCancel()` is called after verifying the needed value. In the second, `take(3)` completes the stream after `2L`.

### Does `Mono.defer` Solve It?

**`Mono.defer`** or **`Flux.defer`** postpones invoking the factory until **subscription**:

~~~java
Mono<Long> safelyDeferred =
        Mono.defer(() -> Mono.delay(Duration.ofHours(5)));
~~~

The `Mono.defer` wrapper itself can be constructed upfront, yet **`Mono.delay` is assembled upon subscribe**, giving it a chance to pick up the active virtual scheduler. However:

- If the inner lambda returns a pre-built `Publisher`, `defer` **does not undo** the scheduler captured earlier by that operator.
- If using a pre-created custom scheduler or an HTTP client tied to real clocks, `defer` **does not virtualize** that work.
- With **`StepVerifier.withVirtualTime`**, the clearest pattern remains **a `Supplier` assembling the full pipeline under test**, rather than relying on `defer` tricks to mask eager assembly.
- When an API/service must always return a pre-constructed publisher, `defer` is reasonable **after** verifying which operators it creates at subscription time.

Do not confuse **lazy assembly inside a `Supplier`** with **lazy subscription inside `Mono.defer`**. Both relate to creation timing, but at different API layers.

## 6. Runnable Example: Java 17 + Spring Boot 3.4.5 + Reactor Test

This small project needs no web server, database, or Testcontainers. It uses Reactor Core for business flows, Reactor Test for `StepVerifier`, and JUnit Jupiter for tests. Spring Boot provides dependency management and a Spring bean to illustrate testing a service in context.

**Contract of `TimedStreamService`:**

1. **`delayed(value, wait)`** emits `value` after a positive `wait`.
2. **`ticks(period, count)`** emits `0L` through `count-1` every positive `period` and completes; `count` must be greater than 0.
3. **`timeoutFallback(timeout)`** on a `never()` source must return `"fallback"` upon `timeout`.
4. **`retryTwice(operation, wait)`** retries an operation up to twice after each fixed `wait`; when the third attempt succeeds, it emits `"ok"`.

This contract makes `onNext` ordering and timing easy to verify. External factors such as HTTP clients or sleeps are omitted to avoid random delays.

### 6.1. File Tree

~~~text
settings.gradle
build.gradle
src/main/java/com/example/virtualtime/VirtualTimeApplication.java
src/main/java/com/example/virtualtime/TimedStreamService.java
src/test/java/com/example/virtualtime/TimedStreamServiceTest.java
src/test/java/com/example/virtualtime/TimedStreamSpringContextTest.java
~~~

**`settings.gradle`**

~~~groovy
rootProject.name = 'reactor-virtual-time-learning'
~~~

**`build.gradle`**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'io.projectreactor:reactor-core'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Keep Reactor Core and `reactor-test` aligned with the Spring Boot BOM to prevent version mismatches. **`reactor-test`** is only needed on the test classpath, not as an `implementation` dependency of the production service. Reactor virtual time works without starting a Spring context; therefore, the unit tests below do not use `@SpringBootTest`, except for the separate wiring test.

**`src/main/java/com/example/virtualtime/VirtualTimeApplication.java`**

~~~java
package com.example.virtualtime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class VirtualTimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(VirtualTimeApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/virtualtime/TimedStreamService.java`**

~~~java
package com.example.virtualtime;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.TimeoutException;
import java.util.function.Supplier;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

@Service
public class TimedStreamService {
    public Mono<String> delayed(String value, Duration wait) {
        positive(wait);
        Objects.requireNonNull(value, "value");
        return Mono.delay(wait).map(ignored -> value);
    }

    public Flux<Long> ticks(Duration period, int count) {
        positive(period);
        if (count <= 0) {
            throw new IllegalArgumentException("count must be positive");
        }
        return Flux.interval(period).take(count);
    }

    public Mono<String> timeoutFallback(Duration timeout) {
        positive(timeout);
        return Mono.<String>never()
                .timeout(timeout)
                .onErrorResume(TimeoutException.class,
                        ignored -> Mono.just("fallback"));
    }

    public Mono<String> retryTwice(
            Supplier<Mono<String>> operation, Duration wait) {
        Objects.requireNonNull(operation, "operation");
        positive(wait);
        return Mono.defer(operation)
                .retryWhen(Retry.fixedDelay(2, wait));
    }

    private static void positive(Duration value) {
        Objects.requireNonNull(value, "duration");
        if (value.isZero() || value.isNegative()) {
            throw new IllegalArgumentException(
                    "duration must be positive");
        }
    }
}
~~~

**Why is this implementation testable with virtual time?** Each call to `delayed`, `ticks`, `timeoutFallback`, or `retryTwice` builds a **new Publisher** with the corresponding time-based operator. Tests **invoke the method inside `withVirtualTime`'s `Supplier`**, so those operators are assembled after the Reactor virtual scheduler is installed.

**Note the distinction:** validation of `value`, `duration`, and `count` in the Java method body runs immediately at **assembly time**, whereas `Mono`/`Flux` signals emit at **subscription time**. A service wanting input errors normalized as `onError` signals instead of synchronous throws can use `Mono.defer`/`Mono.error` per its contract; this example throws directly since the focus is the clock.

### 6.2. Complete Unit Tests Without Booting Spring Context

**`src/test/java/com/example/virtualtime/TimedStreamServiceTest.java`**

~~~java
package com.example.virtualtime;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class TimedStreamServiceTest {
    private final TimedStreamService service = new TimedStreamService();

    @Test
    void createsMonoAfterVirtualClockActivation() {
        StepVerifier.withVirtualTime(() ->
                        service.delayed("ready", Duration.ofDays(1)))
                .expectSubscription()
                .expectNoEvent(Duration.ofHours(23))
                .thenAwait(Duration.ofHours(1))
                .expectNext("ready")
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void emitsThreeTicksAtExpectedVirtualInstants() {
        StepVerifier.withVirtualTime(() ->
                        service.ticks(Duration.ofMinutes(30), 3))
                .expectSubscription()
                .thenAwait(Duration.ofMinutes(30))
                .expectNext(0L)
                .thenAwait(Duration.ofMinutes(30))
                .expectNext(1L)
                .thenAwait(Duration.ofMinutes(30))
                .expectNext(2L)
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void timesOutAndUsesFallbackAfterFiveMinutes() {
        StepVerifier.withVirtualTime(() ->
                        service.timeoutFallback(Duration.ofMinutes(5)))
                .expectSubscription()
                .expectNoEvent(Duration.ofMinutes(4))
                .thenAwait(Duration.ofMinutes(1))
                .expectNext("fallback")
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void retriesTwiceWithoutWaitingTwentyRealMinutes() {
        AtomicInteger attempts = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                        service.retryTwice(() -> {
                            int current = attempts.incrementAndGet();
                            if (current < 3) {
                                return Mono.error(
                                        new IllegalStateException("busy"));
                            }
                            return Mono.just("ok");
                        }, Duration.ofMinutes(10)))
                .expectSubscription()
                .expectNoEvent(Duration.ofMinutes(10))
                .thenAwait(Duration.ofMinutes(10))
                .expectNext("ok")
                .expectComplete()
                .verify(Duration.ofSeconds(5));

        assertEquals(3, attempts.get());
    }

    @Test
    void verifiesAStreamThatIsNotFinite() {
        StepVerifier.withVirtualTime(() ->
                        reactor.core.publisher.Flux.interval(
                                Duration.ofHours(1)))
                .expectSubscription()
                .thenAwait(Duration.ofHours(1))
                .expectNext(0L)
                .thenAwait(Duration.ofHours(1))
                .expectNext(1L)
                .thenCancel()
                .verify(Duration.ofSeconds(5));
    }
}
~~~

**Explanation of each test:**

- **`createsMonoAfterVirtualClockActivation`**: the service method is invoked **inside the `Supplier`**. No `onNext`/`onComplete` arrives for 23 virtual hours; after one more hour, `"ready"` emits and completes.
- **`emitsThreeTicksAtExpectedVirtualInstants`**: `Flux.interval` waits one full period before the first emission; thus `0L` is expected at minute 30, `1L` at minute 60, and `2L` at minute 90. **`take(3)`** causes the stream to complete.
- **`timesOutAndUsesFallbackAfterFiveMinutes`**: `Mono.never` emits nothing; `timeout` uses the virtual clock to raise `TimeoutException`, and `onErrorResume` switches to `"fallback"` at virtual minute 5.
- **`retriesTwiceWithoutWaitingTwentyRealMinutes`**: `Mono.defer(operation)` ensures the `Supplier` is called again **on each subscription/retry**. `AtomicInteger` proves three total attempts, and `Retry.fixedDelay(2, 10 minutes)` creates two wait intervals totaling 20 virtual minutes.
- **`verifiesAStreamThatIsNotFinite`**: `Flux.interval` never ends, so after two values the test calls **`thenCancel`** instead of waiting for an impossible completion.

**`verify(Duration.ofSeconds(5))`** sets the **wall-clock limit** for each verification so a scheduling bug cannot hang the test forever. It does not force publishers to take five real seconds; virtual time advances internally within `StepVerifier`. Depending on machine/CI load, you can choose another realistic watchdog timeout without changing business `Duration` values.

### 6.3. Spring Context Test: Bean Exists Early, Publisher Created Late

**`src/test/java/com/example/virtualtime/TimedStreamSpringContextTest.java`**

~~~java
package com.example.virtualtime;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import reactor.test.StepVerifier;

@SpringBootTest
class TimedStreamSpringContextTest {
    @Autowired
    private TimedStreamService service;

    @Test
    void springBeanCreatesPipelineInsideSupplier() {
        StepVerifier.withVirtualTime(() ->
                        service.delayed("spring-ready", Duration.ofHours(8)))
                .expectSubscription()
                .expectNoEvent(Duration.ofHours(7))
                .thenAwait(Duration.ofHours(1))
                .expectNext("spring-ready")
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }
}
~~~

Spring instantiated the **service bean** before the test ran, yet **the publisher is only built when `delayed` is called inside the `Supplier`**. That is the difference between **bean lifecycle** and **pipeline assembly**. Since the test only checks Reactor operators, plain Java unit tests remain the faster choice; `@SpringBootTest` is only needed to protect Spring wiring.

### 6.4. Running and Expected Outcomes

Use the Gradle Wrapper compatible with Java 17 and Boot 3.4.x. On Linux/macOS:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.virtualtime.TimedStreamServiceTest
./gradlew test --tests com.example.virtualtime.TimedStreamSpringContextTest
~~~

On Windows: replace **`./gradlew`** with **`gradlew.bat`** with the same arguments. These checks are designed to **PASS** when files and dependencies match the sample. This is the expectation from code, **not stdout from an actual build run**.

Your machine will not wait 1 real day, 90 minutes, or 20 minutes. Reactor Test advances the virtual clock during verification. Still, downloading Gradle dependencies, booting the Spring context, and running JUnit take real time.

## 7. When a Spring Bean Holds a Publisher in a Field: A Subtle Bug

Suppose a Spring service is written like this:

~~~java
@Service
class ScheduledMessageService {
    private final Mono<String> cachedPipeline =
            Mono.delay(Duration.ofHours(24))
                .map(ignored -> "sent");

    Mono<String> deliver() {
        return cachedPipeline;
    }
}
~~~

**This is a counterexample**, not part of the runnable project in Section 6. The bean is instantiated by Spring at startup, before the test calls `withVirtualTime`. **`cachedPipeline`** may have already bound a real scheduler at assembly time. Writing:

~~~java
StepVerifier.withVirtualTime(service::deliver)
    .expectSubscription()
    .thenAwait(Duration.ofHours(24))
    .expectNext("sent")
    .verifyComplete();
~~~

is still wrong for timing because `deliver` does not build a new operator. The `Supplier` merely returns **the exact same `cachedPipeline`**.

**Fix with a factory method:**

~~~java
@Service
class ScheduledMessageService {
    Mono<String> deliver() {
        return Mono.delay(Duration.ofHours(24))
                .map(ignored -> "sent");
    }
}
~~~

When a test passes `service::deliver` to `withVirtualTime`, the timed operator is created after setup. Having an autowired service **is not** a problem as long as it **does not pre-assemble timed operators** in fields or constructors.

**If you must hold a `Publisher` field:** consider **`Mono.defer(() -> Mono.delay(...))`** to build the timed operator at subscription time, or design explicit `Scheduler`/`Clock` injection. Still, review the entire chain; if another operator captured a scheduler out of scope, the issue is not solved yet.

## 8. Limits of `VirtualTimeScheduler`: It Is Not the Entire JVM's Clock

**`VirtualTimeScheduler`** primarily controls tasks scheduled onto itself. Reactor Test uses hook/factory mechanisms so default Reactor `Scheduler` instances used by timed operators are replaced with the virtual scheduler during the test. However, it **does not alter the OS clock**, nor speed up `Thread.sleep`, `Socket.timeout`, JDBC drivers, arbitrary external I/O, or `java.time.Instant.now()`.

Example:

~~~java
Mono<String> notVirtualized = Mono.fromSupplier(
        () -> java.time.Instant.now().toString());
~~~

This `Mono` reads wall-clock time on subscription; `thenAwait` does not make `Instant.now` jump one day ahead of the OS clock. When business logic depends on date/time, **inject `java.time.Clock`** and use `Clock.fixed` or `Clock.offset` in unit tests. Reactor virtual time and domain `Clock` are **two different clocks**.

### Pre-Created Custom Schedulers Are Not Automatically Replaced

~~~java
Scheduler realScheduler = Schedulers.newSingle("dedicated-real");

try {
    Mono<Long> timer = Mono.delay(
            Duration.ofHours(3), realScheduler);

    // Do not assume thenAwait(3h) controls this timer.
} finally {
    realScheduler.dispose();
}
~~~

This snippet is **illustrative** and requires `reactor.core.scheduler.Scheduler` and `Schedulers` imports; it is not part of the runnable project. A scheduler created via `newSingle` is a resource that must be disposed. If an operator uses a dedicated scheduler or executor outside Reactor's virtualized factory, even lazy assembly inside the `Supplier` does not guarantee virtual time.

To test dependencies using a custom scheduler, use **Scheduler injection** and supply a `VirtualTimeScheduler` in tests, or test with a real scheduler using short timeouts and appropriate expectations. Choose based on the contract rather than labeling something "virtual time" when it has no connection to the virtual clock.

### Scheduling Order Inside `flatMap` and Nested Operators

Some pipelines only create a timer **after another `onNext` arrives**, such as a delay inside `flatMap`. If you call `thenAwait` before the inner timer is scheduled, the virtual clock may jump past a point after which the inner timer starts counting from **the already-advanced timestamp**, causing signals not to appear when expected. The `StepVerifier` Javadoc also warns about sources scheduling on different schedulers and delays created **within the data path**.

Structure assertions and clock advances stage by stage: verify the upstream emission first, then advance time for the timer created by that emission. When logic involves multiple schedulers or concurrent branches, a separate test using an explicit `VirtualTimeScheduler` can make scheduling clearer.

## 9. `Flux.interval`, Backpressure, and Infinite Streams

**`Flux.interval(period)`** emits its first **`0L` after the first `period`**, not `0L` immediately at `t=0`. Under virtual time:

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofMinutes(15)).take(2))
    .expectSubscription()
    .expectNoEvent(Duration.ofMinutes(14))
    .thenAwait(Duration.ofMinutes(1))
    .expectNext(0L)
    .thenAwait(Duration.ofMinutes(15))
    .expectNext(1L)
    .verifyComplete();
~~~

This snippet sits inside a JUnit test with `Flux`, `Duration`, and `StepVerifier` imports. It verifies both **no early emission** and **exact cadence**.

If you test an infinite interval and expect **`verifyComplete`**, the test will never receive `onComplete` (unless there is `take`, `timeout`, or another terminating operator). Use **`take(n)`** if the contract bounds elements, or **`thenCancel()`** to verify a slice and cancel the subscription.

With `StepVerifier.withVirtualTime(supplier, 0)`, initial demand is zero. A source like `Flux.interval` can emit a backpressure error if a tick fires with no demand. Call **`thenRequest(n)`** before advancing virtual time, or keep default demand when the test is not examining backpressure. Do not mistake an overflow caused by deliberately withholding demand for a timer bug.

## 10. Retry, Jitter, and Timing Drift

**`Retry.fixedDelay(2, Duration.ofMinutes(10))`** retries up to twice, waiting 10 minutes each time. When the operation succeeds on the third subscription, `StepVerifier` advances the clock 20 minutes total to observe `"ok"`. That is the behavior of the example test in Section 6.

**`Retry.backoff(...)`** uses growing backoff intervals and can add **random jitter**. When tests must assert exact timestamps, use `fixedDelay` or deliberately configure jitter per the API version (e.g., `.jitter(0d)`) and test the backoff rules. Avoid asserting fixed seconds if production code intentionally enables jitter.

Never create and **subscribe to the operation** before `withVirtualTime` just to prepare test data, because that subscription may run real retries or timers. When retry counts matter, use an `AtomicInteger` counting `Supplier` invocations or a recording fake; distinguish **subscription count** from **`Mono` object creation count**.

## 11. Virtual Time, Parallel Tests, and Shared Resources

Reactor virtual time swaps Reactor's shared Scheduler factory for the duration of the test. Consequently, two tests manipulating the scheduler factory on separate threads, or one test running a real-time job while another activates virtual time, can yield scheduling-dependent CI behavior.

Practical guidance:

- Avoid running virtual-time tests in parallel with each other or with tests relying on the same default Reactor `Schedulers`, unless you have a verified isolation strategy.
- Do not manually invoke `Schedulers.resetFactory()`, `resetFactoryWithSnapshot(...)`, or `VirtualTimeScheduler.getOrSet()` while another verification is active to "patch" a test.
- Do not store a `VirtualTimeScheduler`, `Flux`, or `Mono` containing timed operators in static mutable fields shared across a suite.
- Prefer creating each pipeline inside its own `Supplier` and letting `StepVerifier` manage the virtual scheduler lifecycle; if manipulating global schedulers manually, clean up strictly without colliding across threads.
- When tests reuse a cached Spring context, remember **singleton beans are reused**, so any publisher cached inside a bean may have been assembled eagerly at context startup; do not confuse a fresh `PER_METHOD` test instance with a newly recreated pipeline.
- When mixing parallel threads, controlled real-time schedulers, or asynchronous suites, manage test concurrency via build/JUnit configuration rather than relying on test execution order.

`StepVerifier` itself does not guarantee **every** piece of reactive code in the JVM shares one virtual clock. It only controls operators that actually schedule onto the hooked scheduler.

## 12. Avoiding Deadlocks or Tests That Wait Forever

Several coding mistakes prevent the clock from advancing or signals from arriving:

**A. Expecting `onNext` before advancing time.**

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofHours(1)))
    .expectNext(0L) // Waits for a value needing 1 virtual hour, without advancing the clock.
    .verifyComplete();
~~~

This is a **counterexample**. `expectNext` waits for an event that only arrives after the clock passes one hour. Fix it by calling **`expectSubscription().thenAwait(Duration.ofHours(1))`** before `expectNext`.

**B. Creating an interval inside `flatMap` after advancing the clock too far.** The inner timer may schedule once virtual time is already at the new mark, shifting when it fires. Trace the exact order of `onNext` → inner subscription → scheduler registration.

**C. Mixing `Thread.sleep` or blocking calls into a Reactor event-loop/virtual scheduler.** `VirtualTimeScheduler` does not fast-forward sleeps, and blocking the thread needed to execute verification can deadlock the test. Never call `block()` inside an operator waiting on the very clock the test must advance.

**D. Building the publisher before `withVirtualTime`.** This is the central pitfall of the lesson: the scheduler may already be captured in real time. Rebuild the publisher inside the `Supplier`, rather than increasing test timeouts.

**E. Forgetting a terminal expectation.** An infinite `Flux.interval` will not complete. Use `thenCancel` or `take`. If a test calls `verifyComplete` on an infinite stream, the bug is the missing completion contract, not Reactor's virtual-time infrastructure.

**F. Skipping a real-time verification cap.** Even when virtual time speeds things up, a bug can make a test hang forever. `.expectComplete().verify(Duration.ofSeconds(5))` provides a practical safety net that fails fast; tune the duration for CI.

## 13. Symptoms and Quick Diagnostics

| Symptom | Check First | Fix |
| --- | --- | --- |
| `thenAwait(1 day)` still waits in real time | Was the Publisher/`Mono.delay` created before the `Supplier`? | Create time-based operators inside the lambda |
| `Supplier` only says `() -> cachedMono` | Was `cachedMono` assembled in a bean field/constructor? | Use a factory method or `Mono.defer` properly |
| Test never sees `onNext` | Did you advance time before `expectNext`? | Place `thenAwait`/`expectNoEvent` in the right order |
| First-step `expectNoEvent` fails | Subscription counts as an event | Put `expectSubscription` first |
| `Flux.interval` expects `0L` immediately on subscribe | First interval item emits only after `period` | Advance one `period` before `expectNext(0L)` |
| Infinite stream never completes | Missing `take` or terminal condition | Use `thenCancel` or add `take(n)` |
| Test sees unchanged wall-clock values | Using `Instant.now`/`System.currentTimeMillis` | Inject `Clock` separately; do not confuse with `VirtualTimeScheduler` |
| Test uses a real custom `Scheduler` | Operator uses `Schedulers.newSingle`/executor outside hook | Inject/test scheduler or run a real-time test |
| Retry timing is unstable | `Retry.backoff` has jitter | Use `fixedDelay` or configure jitter per contract |
| Virtual test fails only in full suite | Other tests mutate global Scheduler factory or share bean pipelines | Isolate test concurrency and publisher assembly |
| Timeout in `verify(Duration)` | Missing signal, missing demand, or unscheduled work | Check demand, assembly timing, and clock advancement |
| Test passes yet production HTTP timeouts fail | Virtual time only checks Reactor operators | Add HTTP/server timeout integration tests |
| Wrong value even though timer fires on time | Side effect executed during assembly outside `Supplier` | Move the full chain and tested side effects into scope |

A helpful debugging technique is printing the **pipeline structure** at creation time and inspecting **where schedulers appear** (fields, constructors, static initializers, inside `flatMap`, custom schedulers). Be careful not to turn real-time logs into mandatory assertions: scheduling logs can vary across environments.

## 14. Strategy for Choosing Test Types

**Unit tests with `StepVerifier.withVirtualTime`** fit deadlines, delays, timeouts, retries, intervals, heartbeats, and timing policies. The goal is verifying exact **`onNext`/`onError`/`onComplete` signals** as the virtual clock advances.

**Spring context tests** are needed when wiring or configuration determines how pipelines are constructed and subscribed. If an injected service stores a timed publisher in a field, a context test can expose eager assembly bugs that unit tests instantiating the service directly might miss.

**HTTP/WebFlux integration tests** are required when the contract covers status codes, bodies, serialization, filters, routing, connection backpressure, streaming, server timeouts, and client disconnects. A green `StepVerifier` unit test **does not** prove those layers.

**Scheduler/`Clock` injection tests** suit applications using custom Schedulers or domain wall clocks. Only apply virtual time if each operator relies on a scheduler it actually controls; never force it onto external timers and I/O.

### Self-Check

**1.** `Mono.delay` is created in a field before the test, and `withVirtualTime` receives `() -> field`. Does it guarantee running on the virtual clock? **No**: the timed operator may have already captured a real scheduler.

**2.** A Spring bean is initialized before the test, yet `delayed()` always constructs a fresh `Mono.delay`, and the test calls `() -> service.delayed(...)`. Is that valid? **Yes**, because the pipeline is assembled inside the supplier.

**3.** `expectNoEvent` is the first step and fails immediately. Why? **Subscription is also an event**; call `expectSubscription` first.

**4.** What might `thenAwait(10 minutes)` on `Flux.interval(10 minutes)` emit first? **`0L`**, provided the timer was scheduled properly and demand exists.

**5.** Can `Mono.defer(() -> Mono.delay(...))` created before `withVirtualTime` work? **Yes**, because the timed `Mono` is assembled upon subscription; still, `defer` cannot fix custom/captured schedulers outside the lambda.

**6.** Does `withVirtualTime` advance `Instant.now` by 24 virtual hours? **No**. Inject `java.time.Clock` when testing wall-clock domain logic.

**7.** Can an infinite interval stream use `verifyComplete`? **No**, unless the pipeline adds a terminating operator like `take`; use `thenCancel`.

**8.** Is `Retry.backoff` with jitter suitable for asserting exact fixed milliseconds? **No**, unless jitter is intentionally disabled or controlled.

**9.** A test's `verify(Duration.ofSeconds(5))` times out—does that mean business logic waited 5 virtual seconds? **No**. That is the test runner's wall-clock timeout.

### Pre-QA Sign-off Checklist

- Are time-based operators **created inside the `Supplier`** passed to `withVirtualTime`?
- Does the service cache any publisher in a field, constructor, or static initializer before virtual setup?
- Does the publisher use Reactor's default Scheduler or a non-virtualized custom scheduler/Executor?
- Did `StepVerifier` call `expectSubscription` before `expectNoEvent`?
- Do `thenAwait` steps suffice for timers to be scheduled, executed, and emit `onNext`?
- Are retry counts, `delaySubscription`, `timeout`, and jitter handled per contract?
- Is an infinite `Flux` bounded with `take(n)` or `thenCancel`?
- Is demand requested before interval ticks when using `initialRequest=0`?
- Does the test include a wall-clock `verify` limit so CI cannot hang?
- Are any `Thread.sleep`, `block`, I/O, `Instant.now`, or custom `Clock` calls outside the virtual scheduler mechanism?
- Are parallel tests sharing Reactor's `Scheduler` factory or cached Spring beans?
- Are conclusions about Reactor signals kept distinct from conclusions about real HTTP/container/DB behavior?

**Conclusion:** For `StepVerifier.withVirtualTime` to truly govern `delay`/`interval`/`timeout`/`retry`, **do not pre-build timed publishers and merely return them from the `Supplier`**. **Build the entire pipeline under test inside the `Supplier` lambda**, then use `expectSubscription`, `expectNoEvent`, `thenAwait`, and terminal expectations to verify signals. `VirtualTimeScheduler` accelerates **Reactor scheduling**, not wall clocks, every thread, custom schedulers, or external I/O. Keeping pipeline assembly lazy at the right moment and bounding test claims clearly helps catch timing bugs fast without creating a flaky suite.

## Official Documentation

- Project Reactor — Testing, Manipulating Time: https://projectreactor.io/docs/core/release/reference/testing.html
- Reactor Test — `StepVerifier` Javadoc and `withVirtualTime` Supplier: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
- Reactor Test — `VirtualTimeScheduler` Javadoc: https://projectreactor.io/docs/test/release/api/reactor/test/scheduler/VirtualTimeScheduler.html
- Spring Boot 3.4 — Testing: https://docs.spring.io/spring-boot/3.4/reference/testing/index.html