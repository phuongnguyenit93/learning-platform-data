# Verification Timeouts and Post-Test Scheduler Cleanup

Within the **Reactive Flows** topic of Spring Boot testing, `Mono`/`Flux` tests must protect **two distinct contracts**: (1) publisher outputs and signals must be verified within a finite wait budget; (2) schedulers, subscriptions, and resources created by tests must be **cleaned up according to ownership**, preventing thread leaks or breaking other tests.

Using `StepVerifier.verify()` without a deadline allows a stuck pipeline to hang tests indefinitely. Conversely, calling `Schedulers.shutdownNow()` after every test can tear down shared Reactor schedulers across the same JVM. The typical symptom is tests passing in isolation while failing intermittently across the full suite or in parallel execution.

**Three distinct tools must not be conflated:**

- **`StepVerifier.verify(Duration)`:** bounds the *wall-clock time* the verifier waits for the scenario to finish; expiration fails the test with an assertion error.
- **`.timeout(Duration)` operator:** part of the business pipeline itself; expiration produces `onError(TimeoutException)` or invokes a configured fallback.
- **`StepVerifier.withVirtualTime(...)` / `VirtualTimeScheduler`:** simulates the clock observed by compatible schedulers, letting tests verify long timers, delays, and backoffs without sleeping in real time.

This lesson explains choosing timeouts, managing `Scheduler.dispose()` and `VirtualTimeScheduler.reset()`, leaving shared schedulers intact, and provides **Java 17+, JUnit Jupiter + `reactor-test`** code runnable in a Spring Boot project with matching dependencies.

## 1. Signals to Verify in a Reactive Stream

Reactive Streams unfold when a subscriber registers for data:

```text
Test subscriber                     Publisher
      |                                 |
      |---------- subscribe ---------->|
      |<--------- onSubscribe ----------|
      |----------- request(n) --------->|
      |<------------ onNext(A) ---------|
      |<------------ onNext(B) ---------|
      |<--- onComplete() OR onError() --|
      |
      +-- May cancel subscription before terminal event
```

On a spec-compliant publisher, `onComplete` and `onError` are **mutually exclusive endings**. `Mono<T>` emits at most one `onNext`; `Flux<T>` can emit 0, 1, many, or infinite elements. Publishers like `Mono.never()` and `Flux.never()` never emit a terminal signal on their own.

Sample `StepVerifier` scenarios:

```java
StepVerifier.create(Mono.just("ok"))
        .expectNext("ok")
        .verifyComplete();

StepVerifier.create(Flux.just(1, 2, 3))
        .expectNext(1, 2, 3)
        .verifyComplete();

StepVerifier.create(Mono.empty())
        .verifyComplete();
```

These snippets belong inside test methods with Reactor imports. Synchronous cases finish immediately. When sources involve HTTP, DB, timers, event streams, or demand-gated chains, add a **verification deadline** whenever hanging is a real risk.

Merely building `StepVerifier.create(...).expectNext(...)` without calling `verify()`/`verifyComplete()` executes nothing. The goal is not attaching a decorative timer, but actually subscribing, checking `onNext` signals, and observing the right terminal signal.

## 2. Comparing Timeouts and Their Scopes

| Mechanism | What It Limits | On Expiration | Alters Business Publisher? |
| --- | --- | --- | --- |
| `verify(Duration.ofSeconds(3))` | One `StepVerifier` verification run | Fails with `AssertionError` | **No** |
| `StepVerifier.setDefaultTimeout(...)` | Verifiers created **after** setting global policy | Applies default to new `verify()` calls | No, though it alters global test config |
| `Mono.timeout(Duration)` | Pipeline wait window for upstream signal | `onError(TimeoutException)` if no fallback | **Yes** |
| `withVirtualTime(...)` | Clock of compatible schedulers | Test advances virtual time explicitly | Affects observed operator timing in test |
| JUnit Jupiter `@Timeout` | Entire test method/lifecycle per runner | JUnit fails test as timed out | Does not fix Reactor signals |
| Build/CI timeout | Test task or entire build | Test runner aborts hung task | Not a Reactor assertion |

**Units matter greatly:** `StepVerifier.verify(Duration.ofSeconds(3))` always enforces **three wall-clock seconds**, even when advancing three virtual days inside the scenario. `thenAwait(Duration.ofDays(3))` under `withVirtualTime` can finish nearly instantaneously if operators use the virtual scheduler.

**No finite default timeout:** Reactor Test documents that `StepVerifier.verify()` defaults to waiting indefinitely. Especially when calling `StepVerifier.create(publisher, 0)` without `thenRequest(n)`, a scenario expecting `onNext` can stall forever.

## 3. Using `verify(Duration)` to Guard Individual Tests

Rather than relying on a global timeout that can interfere with other tests, attach the budget directly at verification time:

```java
StepVerifier.create(Flux.just(10, 20, 30))
        .expectNext(10, 20, 30)
        .expectComplete()
        .verify(Duration.ofSeconds(3));
```

`expectComplete()` declares the terminal signal; `verify(Duration)` subscribes, checks all signals, and returns the real elapsed verification duration. This matches declaring terminal expectations and verifying, while capping how long it may wait.

**Distinguish these APIs:**

- `verifyComplete()`: shortcut declaring completion and verifying using the configured default timeout. Do not assume it enforces a finite deadline unless a default was set.
- `expectComplete().verify(Duration)`: controls timeout **per test**, usually the easiest option to maintain.
- `expectError(IllegalArgumentException.class).verify(Duration)`: requires error termination within budget; never expect completion after error.
- `thenCancel().verify(Duration)`: explicitly cancels a non-terminating stream; test verifies the cancellation path.
- `verify(Duration.ZERO)`: per Reactor API, `Duration.ZERO` means **wait indefinitely**, not a 0 ms deadline.

The 3-second cap above **is not a business SLA**. It is a CI safety net so a buggy non-terminating source fails quickly. Business deadlines must reflect application requirements and have dedicated tests.

### Catching an Intentional Verification Timeout

```java
@Test
void neverCompletingPublisherHitsVerificationGuard() {
    assertThrows(AssertionError.class,
            () -> StepVerifier.create(Mono.never())
                    .expectComplete()
                    .verify(Duration.ofMillis(150)));
}
```

This snippet needs `org.junit.jupiter.api.Test` and static `assertThrows` imports. **The JUnit test passes because an assertion failure from `StepVerifier` is the expected outcome here**. Without the timeout bound, calling `verify()` on `Mono.never()` holds the thread forever.

Avoid matching exact wording inside the `AssertionError` message: message text can vary across Reactor releases; what matters is that the verifier enforces its wait budget and fails with the right error type.

## 4. Global `StepVerifier` Timeout: Usable, Must Be Cleaned Up

Reactor Test provides:

```java
StepVerifier.setDefaultTimeout(Duration.ofSeconds(3));
// StepVerifiers created AFTER this call inherit the new default.

StepVerifier.resetDefaultTimeout();
// Reverts to "unlimited" default for subsequent verifiers.
```

This is a **JVM-wide static/global setting**, not scoped to a JUnit test method. Note:

1. The new policy applies only to verifiers built afterward; it **does not retroactively alter already-created verifiers**.
2. It affects other test classes running in the same JVM.
3. `resetDefaultTimeout()` restores **unlimited**, not a prior custom timeout configured by another suite.
4. Parallel tests can race: Test A sets 3s, Test B builds a verifier, Test A resets before Test B finishes building/verifying.
5. An `@AfterEach` reset cleans up the current test's change, yet **cannot make global mutable state safe in parallel suites**.

Example class **strictly for sequential suites intentionally owning the default policy**:

```java
package example.testing.time;

import java.time.Duration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class GlobalVerifierBudgetTest {
    @BeforeEach
    void setBudget() {
        StepVerifier.setDefaultTimeout(Duration.ofSeconds(3));
    }

    @AfterEach
    void resetBudget() {
        StepVerifier.resetDefaultTimeout();
    }

    @Test
    void shortcutUsesConfiguredGlobalBudget() {
        StepVerifier.create(Flux.just("A", "B"))
                .expectNext("A", "B")
                .verifyComplete();
    }
}
```

This is a standalone JUnit file in a project with Reactor/JUnit dependencies. It illustrates the API and state-restoration responsibility, **not** a recommendation to use global timeouts everywhere. In large suites, prefer local `expectComplete().verify(Duration.ofSeconds(...))`.

## 5. Schedulers Are Resources with Ownership

Reactor `Scheduler`s schedule tasks for operators like `publishOn`, `subscribeOn`, `delayElements`, `Mono.delay`, and `Flux.interval`. Distinguish **test-owned** schedulers from **shared/global** ones.

| Resource | Ownership | Proper Cleanup |
| --- | --- | --- |
| `Schedulers.newSingle("test-owned")` | Created by test | `scheduler.dispose()` in `@AfterEach` or `finally` |
| `Schedulers.newParallel("test-owned", 2)` | Created by test | Dispose once no tasks remain |
| `Schedulers.newBoundedElastic(...)` created by test | Created by test | Dispose or manage graceful lifecycle |
| `Scheduler.Worker` created via `createWorker()` | Created by test | `worker.dispose()` |
| `Schedulers.parallel()` | Reactor's shared/cached scheduler | **Never dispose indiscriminately** |
| `Schedulers.boundedElastic()` | Reactor's shared/cached scheduler | Never shut down from an arbitrary test |
| `VirtualTimeScheduler.create()` | Created by test | `virtual.dispose()`; if installed globally, restore factory |
| Manual `publisher.subscribe(...)` | Subscriber/test owns `Disposable` | `subscription.dispose()` when finished |
| Spring WebFlux/Netty server/context | Spring/Netty lifecycle | Closed via the context/server lifecycle |

Failing to dispose a test-created `Schedulers.newSingle(...)` can keep non-daemon threads alive, preventing builds from exiting or leaking threads. Conversely, calling `dispose()` on `Schedulers.parallel()` can cause `RejectedExecutionException` or missed tasks in other tests.

**Rule:** whoever creates an object/resource is responsible for releasing it; for framework-provided shared resources, rely on the framework's lifecycle instead of tearing them down inside individual test fixtures.

## 6. Spring Boot/Reactor Java 17+ Example: A Scheduler-Controlled Service

The examples below focus solely on **publisher signals and scheduler cleanup**. No `ApplicationContext` is needed to test a pure Reactor class.

Project structure:

```text
src/
├── main/java/example/testing/time/
│   ├── DelayService.java
│   └── ExecutorCleanupDemo.java
└── test/java/example/testing/time/
    ├── DelayServiceTest.java
    ├── VirtualTimeScenarioTest.java
    └── GlobalVerifierBudgetTest.java
```

### 6.1. Production File `DelayService.java`

Create `src/main/java/example/testing/time/DelayService.java`:

```java
package example.testing.time;

import java.time.Duration;
import java.util.Objects;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;

public final class DelayService {
    private final Scheduler scheduler;

    public DelayService(Scheduler scheduler) {
        this.scheduler = Objects.requireNonNull(
                scheduler, "scheduler");
    }

    public Flux<Integer> numbers() {
        return Flux.range(1, 3)
                .map(number -> number * 10)
                .publishOn(scheduler);
    }

    public Mono<String> after(Duration delay) {
        if (delay == null || delay.isNegative()) {
            return Mono.error(new IllegalArgumentException(
                    "delay must be >= 0"));
        }

        return Mono.delay(delay, scheduler)
                .map(tick -> "ready");
    }

    public Mono<String> neverCompletes() {
        return Mono.never();
    }
}
```

This class accepts its scheduler via the constructor. `numbers()` emits 10, 20, 30 and completes. `after(delay)` validates delay upfront (`null` or negative becomes `Mono.error(IllegalArgumentException)`), while valid delays use `Mono.delay(delay, scheduler)` to emit a tick and map to `"ready"`. `neverCompletes()` demonstrates verifier hangs without a deadline.

Crucially, `DelayService` **does not close the scheduler**: the caller/composition root decides ownership. In tests, we create a dedicated scheduler and dispose it in the fixture. In a Spring Boot app, if a scheduler is registered as a bean, its lifecycle aligns with the bean/context; never let Spring manage it while a test sharing that context disposes it mid-suite.

### 6.2. Test File `DelayServiceTest.java`

Create `src/test/java/example/testing/time/DelayServiceTest.java`:

```java
package example.testing.time;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;
import reactor.test.scheduler.VirtualTimeScheduler;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class DelayServiceTest {
    private Scheduler ownedScheduler;
    private DelayService service;

    @BeforeEach
    void setUp() {
        ownedScheduler = Schedulers.newSingle("lesson-owned");
        service = new DelayService(ownedScheduler);
    }

    @AfterEach
    void tearDown() {
        if (ownedScheduler != null) {
            ownedScheduler.dispose();
        }
    }

    @Test
    void valuesCompleteWithinVerificationBudget() {
        StepVerifier.create(service.numbers())
                .expectNext(10, 20, 30)
                .expectComplete()
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void negativeDelayIsReactiveError() {
        StepVerifier.create(
                        service.after(Duration.ofSeconds(-1)))
                .expectErrorMatches(error ->
                        error instanceof IllegalArgumentException
                        && "delay must be >= 0"
                                .equals(error.getMessage()))
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void stalledMonoFailsBoundedVerification() {
        assertThrows(AssertionError.class,
                () -> StepVerifier.create(
                                service.neverCompletes())
                        .expectComplete()
                        .verify(Duration.ofMillis(150)));
    }

    @Test
    void cancellationIsObservedByPublisher() {
        AtomicInteger cancels = new AtomicInteger();

        Flux<Integer> endless = Flux.<Integer>never()
                .doOnCancel(cancels::incrementAndGet);

        StepVerifier.create(endless)
                .expectSubscription()
                .thenCancel()
                .verify(Duration.ofSeconds(3));

        assertEquals(1, cancels.get());
    }

    @Test
    void explicitVirtualSchedulerNeedsNoRealTwoHourWait() {
        VirtualTimeScheduler virtual =
                VirtualTimeScheduler.create();

        try {
            DelayService virtualService =
                    new DelayService(virtual);

            StepVerifier.create(
                            virtualService.after(
                                    Duration.ofHours(2)))
                    .expectSubscription()
                    .then(() -> virtual.advanceTimeBy(
                            Duration.ofHours(2)))
                    .expectNext("ready")
                    .expectComplete()
                    .verify(Duration.ofSeconds(3));
        } finally {
            virtual.dispose();
        }
    }
}
```

This suite contains **5 `@Test` methods**:

- `valuesCompleteWithinVerificationBudget`: verifies three items in order followed by completion within the 3-second budget.
- `negativeDelayIsReactiveError`: verifies **`onError`** without wrapping `service.after(...)` in `assertThrows`, since the method returns `Mono.error(...)`.
- `stalledMonoFailsBoundedVerification`: verifies the verifier fails after its timeout via an intentional `assertThrows(AssertionError.class, ...)`.
- `cancellationIsObservedByPublisher`: verifies `thenCancel()` triggers `doOnCancel`, avoiding confusion between cancel and complete.
- `explicitVirtualSchedulerNeedsNoRealTwoHourWait`: creates an isolated virtual scheduler, injects it into the service, advances two virtual hours without `Thread.sleep`, and disposes it in `finally`.

**Teardown note:** `@AfterEach` disposes `ownedScheduler` even when assertions fail. The per-test virtual scheduler is disposed in `finally`. Never call `Schedulers.shutdownNow()`, as that acts globally far beyond this class's own resources.

### 6.3. Test File `VirtualTimeScenarioTest.java`

`StepVerifier.withVirtualTime(...)` swaps the clock for operators using compatible scheduler factories. Create `src/test/java/example/testing/time/VirtualTimeScenarioTest.java`:

```java
package example.testing.time;

import java.time.Duration;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.scheduler.VirtualTimeScheduler;

class VirtualTimeScenarioTest {

    @AfterEach
    void restoreVirtualSchedulerFactory() {
        VirtualTimeScheduler.reset();
    }

    @Test
    void twoTicksAcrossTwoVirtualHours() {
        StepVerifier.withVirtualTime(
                        () -> Flux.interval(
                                Duration.ofHours(1))
                                .take(2))
                .expectSubscription()
                .expectNoEvent(Duration.ofHours(1))
                .expectNext(0L)
                .thenAwait(Duration.ofHours(1))
                .expectNext(1L)
                .expectComplete()
                .verify(Duration.ofSeconds(3));
    }
}
```

This scenario illustrates three principles:

1. **Create the Publisher inside the supplier:** `() -> Flux.interval(...)`, never building `Flux.interval(...)` before virtual scheduler setup.
2. **Expect subscription before `expectNoEvent`:** `StepVerifier` treats subscription as an event, so `expectSubscription()` precedes the quiet window.
3. **Advance virtual hours while bounding real time:** `expectNoEvent(1h)` advances to the first tick, `thenAwait(1h)` advances to the second tick; `verify(3s)` still protects against hangs if the example breaks.

`VirtualTimeScheduler.reset()` is safe cleanup in **a test class intentionally owning the global virtual-scheduler factory**. Because the global scheduler factory affects the entire JVM, **do not run concurrently** with other tests mutating factories or relying on shared Reactor schedulers without coordination. To avoid global mutation altogether, create a local `VirtualTimeScheduler.create()` and inject it directly as shown in the previous test.

### 6.4. Gradle Dependencies and Run Commands

In a Spring Boot project with compatible plugins, repositories, and dependency management configured:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

This is an **incremental configuration snippet**, not a standalone `build.gradle`. The WebFlux starter brings Reactor Core, and `reactor-test` brings `StepVerifier`/`VirtualTimeScheduler`. No `@SpringBootTest` is needed merely to run these unit test classes.

From the project root with Gradle wrapper:

```bash
./gradlew test --tests example.testing.time.DelayServiceTest
./gradlew test --tests example.testing.time.VirtualTimeScenarioTest
./gradlew test --tests example.testing.time.GlobalVerifierBudgetTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.time.DelayServiceTest"
.\gradlew.bat test --tests "example.testing.time.VirtualTimeScenarioTest"
.\gradlew.bat test --tests "example.testing.time.GlobalVerifierBudgetTest"
```

**Expected outcomes when dependencies/configuration match:** `DelayServiceTest` passes 5 test methods, `VirtualTimeScenarioTest` passes 1 case, and `GlobalVerifierBudgetTest` passes 1 case. Do not assume fixed JUnit/Gradle stdout formatting, as runners and logging vary. In suites with parallel execution, isolate tests mutating global schedulers/timeouts or run them individually as above.

## 7. Plain Java 17 Example of Executor Ownership

The Reactor examples require `reactor-core`/`reactor-test` on the classpath and cannot be compiled with bare `javac`. To illustrate **creating a resource → cleaning up that exact resource**, here is a standalone program using Java SE only.

Create `src/main/java/example/testing/time/ExecutorCleanupDemo.java`:

```java
package example.testing.time;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public class ExecutorCleanupDemo {
    public static void main(String[] args)
            throws Exception {
        ScheduledExecutorService executor =
                Executors.newSingleThreadScheduledExecutor();

        try {
            String result = executor.schedule(
                    () -> "ready", 0, TimeUnit.MILLISECONDS)
                    .get(2, TimeUnit.SECONDS);

            System.out.println(result);
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(
                    2, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }

        System.out.println(
                "shutdown=" + executor.isShutdown());
    }
}
```

Compile and run on JDK 17+:

```bash
javac -d out src/main/java/example/testing/time/ExecutorCleanupDemo.java
java -cp out example.testing.time.ExecutorCleanupDemo
```

Exact stdout under normal execution:

```text
ready
shutdown=true
```

This program demonstrates `try/finally`, a bounded wait on the result, and shutting down the executor **created by the program itself**. It uses no Reactor and **does not replace** testing `Scheduler.dispose()`. `executor.isShutdown()` only confirms shutdown was initiated, not that all tasks finished; to verify termination, check `awaitTermination(...)` and handle lifecycle per requirements.

## 8. `VirtualTimeScheduler`: Local Dispose vs. Resetting the Global Factory

There are two ways to drive virtual time in Reactor Test.

**Approach A — local scheduler with minimal side effects:**

```java
VirtualTimeScheduler virtual =
        VirtualTimeScheduler.create();

try {
    StepVerifier.create(
                    Mono.delay(
                            Duration.ofHours(2), virtual))
            .expectSubscription()
            .then(() -> virtual.advanceTimeBy(
                    Duration.ofHours(2)))
            .expectNext(0L)
            .expectComplete()
            .verify(Duration.ofSeconds(3));
} finally {
    virtual.dispose();
}
```

Here the virtual scheduler is passed directly to the operator without **replacing the JVM-wide `Schedulers.Factory`**. Disposing the locally created instance is proper.

**Approach B — installing the virtual scheduler onto shared factories:**

```java
VirtualTimeScheduler virtual =
        VirtualTimeScheduler.create();
VirtualTimeScheduler.set(virtual);

try {
    StepVerifier.create(
                    Mono.delay(Duration.ofHours(2)))
            .expectSubscription()
            .then(() -> virtual.advanceTimeBy(
                    Duration.ofHours(2)))
            .expectNext(0L)
            .expectComplete()
            .verify(Duration.ofSeconds(3));
} finally {
    VirtualTimeScheduler.reset();
    virtual.dispose();
}
```

This snippet illustrates **exclusive ownership of global factories** and is not recommended as a default in parallel suites. `VirtualTimeScheduler.set(virtual)` installs the virtual scheduler into the appropriate factories, `reset()` restores the previous factories, and `virtual.dispose()` closes the test-created instance. **Resetting the factory and disposing the object are two separate steps.**

`VirtualTimeScheduler.getOrSet()` may return an already-active global scheduler installed by another component. **Never blindly dispose a scheduler whose ownership your test does not hold**; when using global setup, organize setup/teardown sequentially with clear ownership.

## 9. Why Should `Schedulers.shutdownNow()` Not Sit in `@AfterEach`?

Reactor API:

```java
Schedulers.shutdownNow();
```

clears and disposes cached schedulers **globally**. It does not target only a scheduler created with `Schedulers.newSingle(...)`.

This is an anti-pattern:

```java
@AfterEach
void tearDown() {
    Schedulers.shutdownNow();
}
```

If Test A shuts down cached schedulers while Test B is executing `publishOn(Schedulers.parallel())` or `subscribeOn(Schedulers.boundedElastic())`, Test B can encounter rejected tasks or erratic failures. Spring Boot tests using shared schedulers can break too.

**When should `Schedulers.shutdownNow()` even be considered?** Only during teardown of a truly isolated environment where **no threads are still using shared schedulers**, such as an end-of-suite hook with clear ownership. Never treat it as general advice for individual test methods.

`Schedulers.resetFactory()` is likewise a global API for restoring scheduler factories, not a command to "clean up a local scheduler". When a test uses `Schedulers.newSingle(...)`, proper cleanup is `dispose()` on that exact instance. If the test creates a `Scheduler.Worker`, dispose the worker via `worker.dispose()` as well.

### Ownership Example When Creating a `Worker`

```java
Scheduler scheduler = Schedulers.newSingle("worker-owned");
Scheduler.Worker worker = scheduler.createWorker();

try {
    worker.schedule(() -> System.out.println("work"));
} finally {
    worker.dispose();
    scheduler.dispose();
}
```

This is a **resource-cleanup snippet**, not a test proving the scheduled task completed. The task may not execute before `finally` disposes it; to verify execution, synchronize deterministically or verify a bounded publisher contract instead of relying on `System.out.println`.

## 10. When to Use `.timeout(Duration)` in a Pipeline?

The `timeout(Duration)` operator changes **publisher behavior**, not just JUnit's wait budget. For instance, wrapping `Mono.never()` with `timeout` produces `java.util.concurrent.TimeoutException` after the wait window.

```java
@Test
void operatorTimeoutProducesReactiveError() {
    StepVerifier.withVirtualTime(
                    () -> Mono.<String>never()
                            .timeout(Duration.ofMinutes(5)))
            .expectSubscription()
            .thenAwait(Duration.ofMinutes(5))
            .expectError(
                    java.util.concurrent.TimeoutException.class)
            .verify(Duration.ofSeconds(3));
}
```

This is an illustrative test method needing `@Test`, `Duration`, `Mono`, and `StepVerifier` imports. **Two timeout layers coexist here**:

- `.timeout(5 minutes)`: after 5 **virtual** minutes, the pipeline emits `onError(TimeoutException)`.
- `verify(3 seconds)`: the whole verification has at most 3 **real** seconds to observe that error event.

If the pipeline also includes `onErrorResume(TimeoutException.class, error -> Mono.just("cached"))`, the subscriber receives `"cached"` and completes; tests must then expect the fallback instead of `expectError(...)`.

**Never add `.timeout(...)` to a test pipeline merely to force a production scenario without timeouts to finish faster.** Doing so changes the behavior under test. To prevent hangs only, use `verify(Duration)`.

## 11. Subscriptions, Workers, and Graceful Shutdown

`StepVerifier` manages subscriptions automatically during verification, including `thenCancel()`. However, when a test calls `subscribe(...)` directly, it receives a `reactor.core.Disposable` and must stop it when finished:

```java
Scheduler owned = Schedulers.newSingle("stream-owner");
Disposable subscription =
        Flux.interval(Duration.ofSeconds(1), owned)
                .subscribe(value -> System.out.println(value));

try {
    // Test actions with a clear stopping point.
} finally {
    subscription.dispose();
    owned.dispose();
}
```

This is a lifecycle snippet, **not a complete test** with assertions. It needs `Duration`, `Flux`, `Disposable`, `Scheduler`, and `Schedulers` imports. The clean order is **disposing the source/subscription before disposing the scheduler**. Never leave an active `Flux.interval` or hot stream running after a test exits.

For custom schedulers requiring graceful shutdown, some implementations offer `scheduler.disposeGracefully()` returning `Mono<Void>`. Because it is a `Mono`, subscribe with an appropriate deadline if you intend to wait for completion rather than dropping the return value. If graceful shutdown fails to finish in time, fall back to forced disposal per resource contract rather than waiting forever.

**Do not equate scheduler disposal with cleaning up all resources:** DB cursors, HTTP response bodies, sockets, message consumers, Spring `ApplicationContext`, and Reactor Netty connection pools each have their own lifecycles. In Spring Boot integration tests, let contexts and adapters close what they own; never expect `Schedulers.shutdownNow()` to close external I/O.

## 12. JUnit `@Timeout` and Runner-Level Caps

JUnit Jupiter supports method-level timeouts:

```java
@Timeout(value = 5, unit = TimeUnit.SECONDS)
@Test
void runnerHasSafetyNet() {
    StepVerifier.create(Flux.just(1, 2))
            .expectNext(1, 2)
            .verifyComplete();
}
```

This method requires `org.junit.jupiter.api.Timeout`, `Test`, and `java.util.concurrent.TimeUnit` imports. `@Timeout` sets a runner-level limit; it **is not an assertion on `onNext`/`onComplete`** and cannot replace `StepVerifier` signal verification.

When using JUnit's **preemptive** timeout mode or thread-interrupt mechanisms running on separate threads, watch out for Spring Test transactions, `SecurityContext`, or `ThreadLocal` bindings. Work on another thread may not join the test runner's managed transaction, and timing out a test does not guarantee external threads or resources finish cleaning up cleanly.

**Four distinct budgets should be kept separate:**

```text
1. Business timeout    : .timeout(Duration) in the pipeline
2. Verification budget : StepVerifier.verify(Duration)
3. Method timeout      : JUnit @Timeout
4. CI/build timeout    : Runner capping the entire task/suite
```

There is no rigid rule that "every test must time out in 1 second". Choose budgets based on hang risk, CI load, scheduler type, and business requirements. Long timers belong in virtual time, while HTTP/database integration tests need wider budgets and reliable cleanup.

## 13. Parallel Execution: Global Schedulers Can Cause Test Flakiness

These APIs mutate **JVM-wide state or shared factory/cache scopes**:

- `StepVerifier.setDefaultTimeout(...)` and `resetDefaultTimeout()`.
- `VirtualTimeScheduler.set(...)` / `getOrSet()` / `reset()`.
- `Schedulers.setFactory(...)` / `resetFactory()` / `shutdownNow()`.
- Global Reactor hooks once registered.

Example race:

```text
Test A: VirtualTimeScheduler.set(virtualA)
             |
Test B: Flux.delayElements(...) picks up global factory
             |
Test A: VirtualTimeScheduler.reset()
             |
Test B: pipeline timing no longer matches expectations
```

**Race-prevention practices:**

1. Prefer injecting `Scheduler` into services and using per-test `Schedulers.newSingle(...)` or `VirtualTimeScheduler.create()`.
2. Prefer local `verify(Duration)` over global `setDefaultTimeout`.
3. If global mutation is unavoidable, run that group sequentially or use synchronization obeyed by **all tests touching that shared resource**.
4. In `@AfterEach`/`finally`, restore only state your test **actually owns**; never blindly reset another test's factory.
5. Never call `Schedulers.shutdownNow()` to rescue a hung test while the rest of the suite is running.
6. With Spring Boot caching a shared `ApplicationContext`, avoid mutating global schedulers from uncontrolled unit tests in the same process.

JUnit `@ResourceLock` can serialize **tests sharing the exact same lock key**, yet cannot protect against other tests ignoring that key. Whenever possible, avoid global mutation by design.

## 14. Diagnosing Hung Tests or Post-Test Failures

**Scenario A — verification never finishes:** check whether the source is `Mono.never`/`Flux.never`, missing a terminal expectation, or missing `thenRequest(n)`. For infinite streams, use `thenCancel()` or explicit limits instead of `verifyComplete()`.

**Scenario B — `verify(Duration)` times out too fast:** do not blindly bump it to an hour. Check for blocking work, a disposed scheduler, stalled external I/O, or an unadvanced virtual clock. Consider fake dependencies, virtual time, and realistic CI budgets.

**Scenario C — CI fails with `RejectedExecutionException` after another test:** check whether a test mistakenly called `dispose()` on shared `Schedulers.parallel()`/`boundedElastic()` or called `Schedulers.shutdownNow()` in `@AfterEach`.

**Scenario D — after virtual-time tests, other tests observe wrong timers:** check whether the global factory was restored, whether publishers were built inside the supplier, and whether tests ran in parallel.

**Scenario E — build passes yet the JVM process never exits:** look for undisposed `newSingle`/`newParallel` or custom executor threads, active `interval` subscriptions, or unclosed networks/containers. Use thread dumps and lifecycle diagnostics to locate the owner instead of forcefully killing the JVM.

**Scenario F — `TimeoutException` seen and mistaken for a `StepVerifier` timeout:** distinguish `TimeoutException` emitted via `onError` by `.timeout` from `AssertionError` raised when `verify(Duration)` misses its deadline. They have distinct causes and assertions.

## 15. Common Mistakes and How to Avoid Them

**1. Calling `verify()` on `Mono.never()`.** Without a timeout or terminal event, the test waits forever; use `verify(Duration)` to test the guard or `thenCancel()` to test cancellation.

**2. Treating `verify(Duration.ZERO)` as an immediate timeout.** Wrong: `ZERO` in this API means wait forever.

**3. Writing expectations without calling `verify`.** The scenario never executes; the test proves nothing.

**4. Using `expectNextCount(n)` without caring about completion.** When requiring `n` elements and termination, assert the matching terminal signal.

**5. Confusing verifier timeouts with business timeouts.** When the verifier expires, the test fails; the publisher itself does not turn into `TimeoutException`.

**6. Adding `.timeout(...)` just to speed up slow tests.** That alters the production behavior under test.

**7. Setting `StepVerifier.setDefaultTimeout` and forgetting to reset.** Other tests are affected, especially under parallel execution.

**8. Resetting global defaults to unlimited in a suite relying on a custom policy.** `resetDefaultTimeout()` does not restore prior custom timeouts; manage policy per owner.

**9. Calling `Thread.sleep` to wait for hours.** Slow and flaky; use virtual time with lazy suppliers or an injected virtual scheduler.

**10. Building the Publisher before `withVirtualTime`.** The scheduler may already be resolved before the factory switches to virtual mode.

**11. Placing `expectNoEvent` before `expectSubscription`.** Subscription itself is an event; the expected order fails.

**12. Forgetting to advance the clock while awaiting a timer.** Under virtual time, due tasks never fire until `thenAwait` or `expectNoEvent` advances time.

**13. Leaving newly created schedulers undisposed.** Keeps worker threads alive and can prevent the build from exiting.

**14. Disposing shared schedulers.** Breaks unrelated tests using Reactor's global schedulers.

**15. Calling `Schedulers.shutdownNow()` in every `@AfterEach`.** Scope is far too broad; reserve for controlled suite-wide teardown.

**16. Calling `VirtualTimeScheduler.reset()` without understanding factory ownership.** Resetting restores factories; it does not automatically dispose standalone `Scheduler` instances.

**17. Leaving manually created subscriptions undisposed.** An `interval` or hot source can keep emitting after the test completes.

**18. Assuming `@Timeout` guarantees all threads/I/O clean up.** Runner timeouts do not replace explicit lifecycle cleanup of schedulers, subscriptions, HTTP, or DB resources.

## 16. Checklist Before Reporting QA PASS

**Signal expectations:**

- Does the Publisher return a finite `Mono`/`Flux`, or can it never complete?
- Is the test expecting `onComplete`, `onError`, or cancellation?
- Was `verify()`/`verify(Duration)` actually called?
- Could the test stall from missing demand or terminal signals? Is the budget finite?
- Are verifier `AssertionError`s kept distinct from publisher `TimeoutException`s?

**Timing:**

- Does the test use a real clock or virtual clock, and why?
- With `withVirtualTime`, is the publisher created inside the supplier?
- Is virtual time advanced sufficiently and in the right step order?
- Is the timeout tuned sensibly for CI load vs. real business deadlines?

**Cleanup:**

- Which schedulers did the test create, and was each instance `dispose()`d?
- Did the test create any `Scheduler.Worker` or call `subscribe()` manually, and were they cleaned up?
- Did it avoid disposing schedulers returned by `Schedulers.parallel()`/`boundedElastic()`?
- Did it avoid calling `Schedulers.shutdownNow()` after every test?
- When mutating global default timeouts or factories, was owned state cleanly restored?
- Are global-mutating tests isolated from parallel tests using scheduler factories?
- Are Spring Boot, Netty, and DB resources managed through their proper lifecycles?

**Conclusion:** a trustworthy Reactor test needs both a **clear verification budget** and **ownership-based scheduler cleanup**. `expectComplete().verify(Duration)` prevents hangs locally; `withVirtualTime`/`VirtualTimeScheduler` verifies timers without real sleeps; `@AfterEach`/`finally` closes test-owned schedulers, while shared schedulers and global factories remain controlled. Never treat `Schedulers.shutdownNow()` as a per-test cleanup shortcut.

## 17. References

- [Project Reactor — StepVerifier API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): `verify(Duration)`, default timeout, and virtual time.
- [Project Reactor — VirtualTimeScheduler API](https://projectreactor.io/docs/test/release/api/reactor/test/scheduler/VirtualTimeScheduler.html): `create`, `set`, `advanceTimeBy`, `reset`.
- [Project Reactor — Scheduler API](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Scheduler.html): `dispose` and `disposeGracefully`.
- [Project Reactor — Schedulers API](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html): global scheduler factories and `shutdownNow`.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier` and virtual time.
- [JUnit Jupiter — Timeouts](https://junit.org/junit5/docs/current/user-guide/#writing-tests-declarative-timeouts): `@Timeout`.
