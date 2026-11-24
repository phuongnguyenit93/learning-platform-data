# Limitations of Synchronous Executors When Proving Concurrent Behavior in Spring Boot Tests

## 1. Scenario: tests pass yet the application still breaks when two tasks run simultaneously

A Spring Boot application sends emails, computes inventory, updates order statuses, or runs background jobs using `TaskExecutor`, `@Async`, and sometimes `@Scheduled`. To keep tests fast and predictable, developers often replace the real executor with **`SyncTaskExecutor`**. This executor invokes `Runnable.run()` **directly on the calling thread of `execute`** and only returns control once the task finishes. That substitution is useful for testing **sequential** functionality, yet carries a serious limitation: it **never creates two concurrently running tasks** when two submissions occur sequentially from one caller.

Consequently, a test like this can pass even when the real application has a race condition:

~~~java
TaskExecutor executor = new SyncTaskExecutor();

executor.execute(() -> orderService.reserve("SKU-1"));
executor.execute(() -> orderService.reserve("SKU-1"));

assertEquals(2, processedCount.get());
~~~

This is a **conceptual snippet** without `orderService` and `processedCount` defined. With `SyncTaskExecutor`, the first reserve command **finishes completely** before the second submission begins, so the test only checks *serial execution*. It **does not prove** that two simultaneous requests won't duplicate orders, lose updates, or violate inventory limits.

**Main topic:** *"Limitations of synchronous executors when proving concurrent behavior"* in the **"Async and Scheduling"** group of Spring Boot testing.

**What you must master:**

1. Understand `SyncTaskExecutor.execute(...)` is **synchronous execution**, not asynchronous/concurrent execution.
2. Distinguish **synchronous**, **asynchronous**, **concurrent**, **parallel**, **overlapping/in-flight**, **deterministic**, and **thread-safe**.
3. Know why using `SyncTaskExecutor` to test callbacks, exceptions, and final outcomes **has value**, yet cannot prove race freedom, pool rejection, lock contention, or scheduling overlap.
4. Distinguish the `@Async` annotation from the **actual selected executor**; `@Async("syncProofExecutor")` can still run inline on the caller thread.
5. Know calls must go **through the Spring proxy** for `@Async` to apply; self-invocation can bypass async advice.
6. Choose a `ThreadPoolTaskExecutor` with at least **two workers** to prove two tasks are **simultaneously active before being released**.
7. Write tests using **`CountDownLatch`**, `CompletableFuture`, `AtomicInteger`, and finite timeouts, avoiding `Thread.sleep(...)` as proof of concurrency.
8. Also test the negative control **single-thread pool** to see why a gate requiring two arrivals cannot complete.
9. Verify thread identity, `Future` state, exception propagation, queuing, rejection, cleanup, and `@Async` qualification.
10. Understand effects on `ThreadLocal`, Spring test transactions, security context/MDC, `@Scheduled`, thread pools, and other async mechanisms.
11. Build a **Java 17 + Spring Boot 3.3.5 + Gradle** project with **16 JUnit Jupiter test methods** split across three classes.
12. Distinguish what the tests actually proved from what still needs **stress testing, race detection, persistence tests**, or real schedule verification.

**Lesson versions:** Java 17, Spring Boot **3.3.5**, Spring Framework **6.1.x**, Gradle, and JUnit Jupiter. Examples run entirely inside the JVM, **requiring no Docker or external services**. If an application uses Java 21 virtual threads, Spring Boot 3.4/3.5/4.x, or a different executor, consult the corresponding API docs before adapting configuration.

## 2. Five concepts frequently conflated

| Concept | Core meaning | Does it prove two jobs overlap? |
|---|---|---|
| **Synchronous call** | Caller waits for work to finish before continuing | No |
| **Asynchronous call** | Invokes work so caller can continue before work finishes | Not automatically: might use one worker or finish too fast |
| **Concurrency** | Multiple tasks make progress within an observation window, potentially interleaved | Possibly, but must verify timing/overlap |
| **Parallelism** | Multiple tasks execute truly simultaneously on compute resources, typically across cores | Requires stronger evidence than having two threads |
| **Thread safety** | Outcomes/invariants remain valid under allowed interleavings | Cannot be inferred from observing a single overlap |

A `ThreadPoolTaskExecutor` with two workers *allows* two callbacks to be active simultaneously, though it does not guarantee every pair of submissions overlaps. Conversely, `SyncTaskExecutor` executes only one callback on the caller thread at a time when a caller submits twice in a row; it spawns no new thread, maintains no background queue, and exercises no interleaving between two tasks.

**Subtle point:** `SyncTaskExecutor` **does not turn a multi-threaded application into a single-threaded one**. If two different caller threads simultaneously invoke **the same `SyncTaskExecutor`**, each callback runs on its respective caller thread and **can still run concurrently**. The exact limitation is: **it creates no concurrency across sequential submissions from a single caller**, not that concurrency can never exist under any circumstances.

Example:

~~~text
Case A — single test caller T0:
T0: execute(task A) ---> task A finishes
T0: execute(task B) -----------------> task B finishes
No A/B overlap created by the executor.

Case B — two distinct callers:
T1: execute(task A) ------------>
T2:     execute(task B) ------------->
The two tasks may overlap, yet concurrency comes from T1/T2,
not from SyncTaskExecutor's scheduling.

Case C — T0 submits to a two-worker thread pool:
T0: execute(A) -> returns
T0: execute(B) -> returns
W1: task A ====== waits at gate ====== continues
W2: task B ====== waits at gate ====== continues
Two tasks are in-flight simultaneously; tests can verify via latch.
~~~

**Do not equate the number of `execute` calls with the number of threads.** Two `execute` calls on a sync executor may use just one thread, and two calls on a pool executor can still serialize in a queue if the pool has only one worker.

## 3. What does `SyncTaskExecutor` actually do?

In Spring Framework 6.1, `org.springframework.core.task.SyncTaskExecutor` is a `TaskExecutor` implementing `java.util.concurrent.Executor` by **invoking `Runnable.run()` directly on the current thread**.

Conceptual summary:

~~~java
final class ConceptualInlineExecutor implements java.util.concurrent.Executor {
    @Override
    public void execute(Runnable command) {
        command.run(); // Spawns no new Thread, enqueues nothing.
    }
}
~~~

**This is a conceptual class**, not source used in the Section 7 project. Spring already ships `SyncTaskExecutor`; there is no need to copy a substitute executor.

Direct consequences:

- **Thread identity:** Inside the task, `Thread.currentThread()` is the very thread that called `execute(...)`.
- **Synchronous timing:** When `execute(...)` returns normally, the callback is already done; no need to await a `Future`/latch to know it finished.
- **Exception propagation:** On a direct `execute` call, unchecked exceptions from the callback can be thrown **right at the caller's `execute` line**. That differs from submitting a `Callable` to a thread pool and checking `Future.get()`.
- **`ThreadLocal`:** Context bound to the calling thread such as custom `ThreadLocal`s, MDC, or transaction associations may be **visible** inside the callback because no thread hop occurred. This is convenient for sequential tests, yet a **source of false confidence** when production runs tasks on another thread.
- **No background scheduling:** `SyncTaskExecutor` has no worker pool, queue capacity, thread-pool starvation, queue-full rejection, worker concurrency limits, or executor-induced races between sequential submissions.
- **Blocking:** If a callback waits on a latch released only by a **subsequent** callback, the caller blocks inside the first callback and can never submit the second. That is a test-design deadlock, not a concurrency proof.

Example showing exact ordering:

~~~java
List<String> events = new ArrayList<>();
TaskExecutor sync = new SyncTaskExecutor();

events.add("before");
sync.execute(() -> events.add("inside"));
events.add("after");

assertEquals(
        List.of("before", "inside", "after"),
        events);
~~~

This is a **snippet inside a JUnit test** with imports `java.util.List`, `java.util.ArrayList`, `TaskExecutor`, `SyncTaskExecutor`, and assertions; the complete version is in Section 8.

**Why does Spring provide it for tests?** A test solely checking that a listener/callback ran, threw an exception, or produced the right final state may value **determinism** over thread hopping. Using a sync executor reduces environmental variance for **sequential goals**. The tool itself is not "wrong"; what is wrong is concluding from a sequential test that code handles concurrent workers safely.

## 4. `@Async` does not mean a different thread is always used

Spring supports `@Async` via `@EnableAsync` and interceptors/proxies. `@Async` can specify an executor name:

~~~java
@Async("syncProofExecutor")
public CompletableFuture<String> runWithSyncExecutor() {
    return CompletableFuture.completedFuture(
            Thread.currentThread().getName());
}
~~~

This snippet is a method inside a Spring-managed bean, not a standalone file. If `syncProofExecutor` is a `SyncTaskExecutor`, the method body executes **on the caller thread**, even though the annotation is named "Async". Spring can wrap the result in a `Future`/`CompletableFuture`, yet that creates no concurrency.

With:

~~~java
@Async("parallelProofExecutor")
public CompletableFuture<String> runWithPool() {
    return CompletableFuture.completedFuture(
            Thread.currentThread().getName());
}
~~~

if `parallelProofExecutor` is a `ThreadPoolTaskExecutor` with workers, Spring dispatches the invocation to a pool thread. Still, the **`Future` may already be done when the test inspects it** if the work is fast. Therefore `future.isDone()` is an **instantaneous observation of completion state**, not reliable proof of whether the executor has concurrency.

### 4.1. Via proxy or self-invocation?

**Via proxy:** the test calls `asyncService.runWithPool()` on the **Spring-injected bean**, where `@EnableAsync` is enabled and the proxy is not bypassed. Spring's async interceptor picks the executor named in `@Async`.

**Not via proxy:** a method in the same class calls `this.runWithPool()`. In Spring's proxy-based async mode, that is **self-invocation**, bypassing the interceptor; the method body runs immediately on the caller. A test invoking only self-invocation and concluding `@Async` doesn't work is testing the wrong execution path.

### 4.2. What should `@Async` return?

`@Async` methods typically return `void`, `Future<T>`, or `CompletableFuture<T>`. When testing completion and exceptions, **prefer `CompletableFuture`** for an observable signal. With `void` async methods, exceptions do not reach the caller directly; Spring uses `AsyncUncaughtExceptionHandler` or logging per config.

Inside the method implementation, returning `CompletableFuture.completedFuture(value)` is valid: the Spring interceptor uses that result to complete the `Future` handed to the caller. **The executor, not the `completedFuture` call, determines which thread runs the method body**.

### 4.3. How does Spring Boot 3.3 choose a default executor?

Spring Framework `@EnableAsync` searches for a suitable `TaskExecutor`, or an `Executor` bean named `taskExecutor` if needed; otherwise it falls back per Framework rules. Spring Boot **3.3** also auto-configures `AsyncTaskExecutor` when no custom executor exists, typically a `ThreadPoolTaskExecutor` on Java 17. If the app defines a custom `Executor` bean, auto-configuration may back off. When multiple executors exist, default selection depends on bean types, names, and `AsyncConfigurer`.

**Never guess the real executor from `@Async` alone.** In our example, we always write **`@Async("syncProofExecutor")`** or **`@Async("parallelProofExecutor")`** to target explicitly without depending on defaults or other beans. Do not name a synchronous executor `taskExecutor` in a production application and accidentally force all async tasks inline.

## 5. What can be proven with a synchronous test executor?

| Testing goal | Is `SyncTaskExecutor` suitable? | Limitation of the evidence |
|---|---|---|
| Callback is invoked and updates state sequentially | **Yes** | Does not prove behavior with two overlapping callbacks |
| Ordering of callbacks from one caller | **Yes**, if strictly sequential order is required | Does not prove a scheduler/worker pool preserves that order |
| DTO mapping, validation, pure domain logic | **Yes** | This is not a concurrency test |
| Exception when `execute` is called directly | **Yes** | Pool submission normally routes errors into `Future`/callbacks |
| Code relying on caller's `ThreadLocal` | May see the value | **Risks masking bugs** when production uses workers |
| Queue capacity, backpressure, rejection | **No** | Sync executor has no worker queue |
| Race conditions / lost updates between two tasks | **No** with sequential submits | Needs real interleaving/concurrency |
| Lock contention or deadlocks across workers | **No** with sequential submits | Needs at least two tasks truly in-flight |
| Whether `@Async` runs on a different thread | **No** if executor was swapped for sync | Needs real executor/proxy assertions |
| Production pool throughput/latency | **No** | Needs workload benchmarks/load tests |
| Two `@Scheduled` invocations overlapping | **No** merely by swapping task executor | Scheduler and trigger semantics must be tested separately |
| Thread safety across all interleavings | **No** | One overlap test proves only one scenario |

**State the scope of your conclusion.** Passing `assertEquals(2, processedCount)` after two sync runs proves callback logic sequentially reaches 2. It **does not** prove atomic increments or DB transaction isolation under contention.

**A very useful cross-check:** run functional assertions with a sync executor to verify basic logic reliably, then run **a separate test** with a real pool and gate to force overlap and check concurrency invariants. Do not replace all tests with pools (making pure logic tests needlessly flaky), and do not replace all tests with sync (leaving a major class of risks untested).

## 6. Proper method for proving overlap

### 6.1. Using a latch to establish a rendezvous

Two tasks must:
1. Be submitted to a real executor with enough workers.
2. Signal they have **entered the active region** with `entered.countDown()`.
3. Wait on the same `release` latch so **both stay in-flight** while the test thread checks state.
4. Have the test thread await `entered.await(timeout)`, confirming **both tasks started and have not exited yet**.
5. Check `maxInFlight == 2`, `!future1.isDone()`, and `!future2.isDone()` while the gate stays closed.
6. In `finally`, open the gate so **no worker stays stuck** if an assertion fails; apply timeouts to `Future.get`.
7. After releasing, inspect results and all side effects.

~~~text
JUnit test thread T0           pool worker W1          pool worker W2
        |                            |                       |
        | submit task1  ---------->  | enter; active=1        |
        | submit task2  ----------------------------------->  | enter; active=2
        |                            | wait release           | wait release
        | await entered(2) ----------+-----------------------+
        | assert maxInFlight==2      |                       |
        | assert futures not done    |                       |
        | release.countDown() ------>+---------------------->+
        |                            | finish                | finish
        | get both futures ----------+-----------------------+
~~~

**What is proven?** Two tasks were **simultaneously in-flight before completing**, overlapping for a measurable interval while both waited. This proves **overlap** of two task invocations in this setup; it **does not prove two CPU cores executed instructions on the exact same nanosecond** or that code is safe under every possible schedule.

### 6.2. Why not use `Thread.sleep(100)`?

~~~java
executor.execute(() -> {
    Thread.sleep(100); // Assuming task B will interleave...
});
~~~

This is an **anti-pattern snippet** and does not handle the checked exception. Scheduler/CPU/CI load can prevent task B from starting during that sleep; the test may "usually pass" while enforcing no ordering relationship. Latches/barriers create **explicit synchronization conditions**; the timeout in `await(5, SECONDS)` is merely a wait bound, not the concurrency mechanism.

### 6.3. Why not apply a two-party gate to `SyncTaskExecutor`?

If T0 executes:

~~~java
sync.execute(() -> {
    entered.countDown();
    release.await(); // T0 blocks right here.
});
sync.execute(() -> {
    entered.countDown(); // Never submitted by T0.
});
~~~

This is a **warning snippet**; lacks imports and throws `InterruptedException`. The first callback blocks caller T0 at `await`; the second submission can never execute. A `CountDownLatch(2)` waiting for two arrivals can never complete when T0 stalls before submitting the second task. Without a timeout/cleanup, the test hangs forever.

**Never treat "latch did not count down" as proof of an application race/deadlock.** Here the deadlock comes from the test forcing a multi-thread protocol onto an inline executor.

### 6.4. Using AtomicInteger to count in-flight tasks

~~~java
int now = active.incrementAndGet();
maxActive.accumulateAndGet(now, Math::max);

try {
    // Wait on gate; keep active > 0.
} finally {
    active.decrementAndGet();
}
~~~

`AtomicInteger` is used in **test instrumentation** so counting does not introduce its own data race. `maxActive=2` combined with the latch proves overlap inside the marked region. **Do not use the atomic counter itself to pretend business code is race-free**: a safe counter only protects the measurement variable, not orders, inventory, caches, or transactions.

## 7. Runnable Spring Boot 3.3.5 / Java 17 project

The example builds:
- A small Spring Boot app with no HTTP server.
- Two executors with **explicit bean names**: `syncProofExecutor` and `parallelProofExecutor`.
- An **`OverlapGate`** safe for tests; guarantees release even when assertions fail.
- A Spring-managed `AsyncProbeService` with both `@Async` targets and one self-invocation.
- Three JUnit Jupiter classes totaling **16 tests**: 6 sync, 6 pool, and 4 Spring async proxy.
- `junit-platform.properties` so test classes don't accidentally run in parallel and contend over the 2-worker pool.

### 7.1. File tree

~~~text
settings.gradle
build.gradle
src/main/java/demo/async/ExecutorProofApplication.java
src/main/java/demo/async/ProofExecutorConfiguration.java
src/main/java/demo/async/OverlapGate.java
src/main/java/demo/async/AsyncProbeService.java
src/test/resources/junit-platform.properties
src/test/java/demo/async/SyncTaskExecutorTest.java
src/test/java/demo/async/ThreadPoolTaskExecutorTest.java
src/test/java/demo/async/AsyncProxyIntegrationTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'spring-sync-executor-concurrency-proof'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-aop'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

Spring Boot starter provides the application context and logging; `starter-aop` ensures Spring AOP proxy infrastructure for method interception tests; `starter-test` provides JUnit Jupiter, Spring Boot Test, and assertions. This lesson needs no `spring-boot-starter-web`, DataSource, or RabbitMQ. Java 17 supports records, lambdas, and `CompletableFuture`. The Spring Boot BOM keeps Spring Framework versions aligned.

**src/test/resources/junit-platform.properties**

~~~properties
junit.jupiter.execution.parallel.enabled=false
~~~

This file controls JUnit Jupiter parallel execution of **tests** only; it does not stop `ThreadPoolTaskExecutor` from running concurrently inside a test. Production schedulers/worker threads still run concurrently when submitted; Section 9 tests actively create overlap.

### 7.2. Main application

**src/main/java/demo/async/ExecutorProofApplication.java**

~~~java
package demo.async;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ExecutorProofApplication {

    public static void main(String[] args) {
        SpringApplication.run(ExecutorProofApplication.class, args);
    }
}
~~~

No HTTP server starts because no web starter is declared. Under `@SpringBootTest`, Spring locates the main application via the package hierarchy.

### 7.3. Configuring two separate executors

**src/main/java/demo/async/ProofExecutorConfiguration.java**

~~~java
package demo.async;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.SyncTaskExecutor;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class ProofExecutorConfiguration {

    @Bean("syncProofExecutor")
    public TaskExecutor syncProofExecutor() {
        // Runnable executes immediately on the calling thread.
        return new SyncTaskExecutor();
    }

    @Bean("parallelProofExecutor")
    public ThreadPoolTaskExecutor parallelProofExecutor() {
        ThreadPoolTaskExecutor pool =
                new ThreadPoolTaskExecutor();

        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(0);
        pool.setThreadNamePrefix("parallel-proof-");

        pool.setWaitForTasksToCompleteOnShutdown(true);
        pool.setAwaitTerminationSeconds(10);

        // Spring initializes/closes the bean per lifecycle;
        // no need to call initialize() manually in @Bean.
        return pool;
    }
}
~~~

**Why a two-worker pool with `queueCapacity=0`?**
- Two workers are the practical requirement so two tasks can wait at `OverlapGate` concurrently.
- `queueCapacity=0` gives `ThreadPoolTaskExecutor` a **`SynchronousQueue`**, meaning no buffer queues extra tasks when both workers are busy. Submitting a third task while both workers hold the gate makes Spring reject with **`TaskRejectedException`** per default rejection policy. That demonstrates capacity/backpressure and prevents a third task from silently queuing.
- `corePoolSize=maxPoolSize=2` bounds the example pool size. **Never** copy this config straight into production without analyzing I/O, CPU, and backpressure.
- `ThreadPoolTaskExecutor` implements Spring lifecycle; in real `@Bean` definitions, Spring handles initialization and destruction. Test tasks are released and `Future.get` awaited before context shutdown.

**Never replace the entire application executor with `SyncTaskExecutor` in production.** The example creates two beans to compare within one project; every `@Async` method in this lesson **selects its executor by name**, without relying on Boot defaults. In real apps with Spring MVC async, GraphQL, or WebFlux blocking support, Spring Boot places specific expectations on `applicationTaskExecutor`; never flip the global bean to `SyncTaskExecutor` just to mask flaky tests.

### 7.4. OverlapGate to verify concurrency without sleep

**src/main/java/demo/async/OverlapGate.java**

~~~java
package demo.async;

import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class OverlapGate {

    private final CountDownLatch entered;
    private final CountDownLatch release = new CountDownLatch(1);

    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger peakActive = new AtomicInteger();

    public OverlapGate(int expectedArrivals) {
        if (expectedArrivals <= 0) {
            throw new IllegalArgumentException(
                    "expectedArrivals must be positive");
        }
        this.entered = new CountDownLatch(expectedArrivals);
    }

    public String enterAndAwaitRelease() {
        int currentlyActive = active.incrementAndGet();
        peakActive.accumulateAndGet(currentlyActive, Math::max);
        entered.countDown();

        try {
            // Timeout is a safety net, not what creates concurrency.
            if (!release.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Gate was not released in time");
            }
            return Thread.currentThread().getName();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Interrupted while waiting for gate", ex);
        } finally {
            active.decrementAndGet();
        }
    }

    public boolean awaitAllEntered(Duration timeout)
            throws InterruptedException {
        return entered.await(
                timeout.toMillis(), TimeUnit.MILLISECONDS);
    }

    public int peakActive() {
        return peakActive.get();
    }

    public int active() {
        return active.get();
    }

    public void open() {
        release.countDown();
    }
}
~~~

**Why does this code hold up well in tests?** `active` and `peakActive` are `AtomicInteger`, `entered` and `release` are `CountDownLatch` — all measured state uses thread-safe coordination. Each task signals arrival **before** waiting on release; the test waits for both arrivals and then asserts neither has finished. Once signaled, `CountDownLatch` establishes **happens-before** between actions before `countDown` and actions after a successful `await`. `finally` inside the method decrements `active` even on timeout/interrupt; `finally` in the test opens the gate to prevent stranding waiting workers.

**Limitation:** If a test misconfigures the pool with only one worker, a gate expecting two arrivals will not complete; the main test times out cleanly and opens the gate so the first task proceeds. That is an **informative test failure**, not an infinite hang.

### 7.5. Spring-managed service for @Async / proxy tests

**src/main/java/demo/async/AsyncProbeService.java**

~~~java
package demo.async;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncProbeService {

    @Async("syncProofExecutor")
    public CompletableFuture<String> threadFromSyncExecutor() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName());
    }

    @Async("parallelProofExecutor")
    public CompletableFuture<String> threadFromPoolExecutor() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName());
    }

    @Async("parallelProofExecutor")
    public CompletableFuture<String> waitAtGate(OverlapGate gate) {
        return CompletableFuture.completedFuture(
                gate.enterAndAwaitRelease());
    }

    public CompletableFuture<String> selfInvokePoolMethod() {
        // Self-invocation: bypasses @Async proxy.
        return this.threadFromPoolExecutor();
    }
}
~~~

**Notable points:**
- The first three methods are public; when invoked through the **Spring bean/proxy**, `@Async` applies the qualified executor.
- With `syncProofExecutor`, the `Future` may already be returned completed because the task ran inline.
- With `parallelProofExecutor`, the method body runs on a pool thread. It can finish very quickly; checking `isDone` alone is not enough to prove overlapping behavior.
- `waitAtGate` provides an explicit synchronization point so tests can prove **two `@Async` calls are simultaneously in-flight**.
- `selfInvokePoolMethod()` uses `this.threadFromPoolExecutor()` to illustrate **proxy bypass**; the body runs on the caller even though the target method carries `@Async`.
- Methods return `CompletableFuture` so tests can await completion and inspect exceptions; never use async `void` when tests need to confirm completion.

## 8. JUnit class 1: synchronous executor runs sequentially

**src/test/java/demo/async/SyncTaskExecutorTest.java**

~~~java
package demo.async;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.task.TaskExecutor;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@Execution(ExecutionMode.SAME_THREAD)
class SyncTaskExecutorTest {

    @Autowired
    @Qualifier("syncProofExecutor")
    TaskExecutor sync;

    @Test
    void syncExecuteUsesCallerThread() {
        Thread caller = Thread.currentThread();
        AtomicReference<Thread> observed =
                new AtomicReference<>();

        sync.execute(() ->
                observed.set(Thread.currentThread()));

        assertSame(caller, observed.get());
    }

    @Test
    void syncExecuteFinishesBeforeReturn() {
        AtomicBoolean completed = new AtomicBoolean(false);

        sync.execute(() -> completed.set(true));

        // After execute, the Runnable is already finished.
        assertTrue(completed.get());
    }

    @Test
    void twoSynchronousTasksNeverOverlapForOneCaller() {
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maximum = new AtomicInteger();

        Runnable task = () -> {
            int now = active.incrementAndGet();
            maximum.accumulateAndGet(now, Math::max);
            active.decrementAndGet();
        };

        sync.execute(task);
        sync.execute(task);

        assertEquals(1, maximum.get());
        assertEquals(0, active.get());
    }

    @Test
    void exceptionsAreThrownAtExecuteCall() {
        IllegalArgumentException failure = assertThrows(
                IllegalArgumentException.class,
                () -> sync.execute(() -> {
                    throw new IllegalArgumentException("bad job");
                }));

        assertEquals("bad job", failure.getMessage());
    }

    @Test
    void nestedExecuteIsReentrantOnSameCallStack() {
        List<String> order = new ArrayList<>();

        sync.execute(() -> {
            order.add("outer-start");
            sync.execute(() -> order.add("inner"));
            order.add("outer-end");
        });

        assertEquals(
                List.of("outer-start", "inner", "outer-end"),
                order);
    }

    @Test
    void threadLocalRemainsVisibleToInlineTask() {
        ThreadLocal<String> trace = new ThreadLocal<>();
        trace.set("request-A");

        try {
            AtomicReference<String> observed =
                    new AtomicReference<>();

            sync.execute(() -> observed.set(trace.get()));

            assertEquals("request-A", observed.get());
        } finally {
            trace.remove();
        }
    }
}
~~~

**Exactly 6 `@Test` methods.** These tests prove:
- `syncExecuteUsesCallerThread`: thread does not change.
- `syncExecuteFinishesBeforeReturn`: callback completes before `execute` returns.
- `twoSynchronousTasksNeverOverlapForOneCaller`: for **two sequential submissions from one caller**, peak active is only 1. **Do not overgeneralize** that two separate callers could never overlap.
- `exceptionsAreThrownAtExecuteCall`: unchecked exceptions from direct inline `execute` reach the caller immediately.
- `nestedExecuteIsReentrantOnSameCallStack`: inner callback executes nested inside outer callback rather than queuing for a free worker.
- `threadLocalRemainsVisibleToInlineTask`: caller's `ThreadLocal` is present in the inline callback; tests can potentially **mask** a missing context-propagation bug in a production pool.

**Not a single test here proves thread safety of business services.** The six tests verify the semantics of a sync executor and establish a **negative control** for the pool section.

## 9. JUnit class 2: two-thread pool, latches, Futures, and rejection

**src/test/java/demo/async/ThreadPoolTaskExecutorTest.java**

~~~java
package demo.async;

import java.time.Duration;
import java.util.concurrent.Callable;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@Execution(ExecutionMode.SAME_THREAD)
class ThreadPoolTaskExecutorTest {

    @Autowired
    @Qualifier("parallelProofExecutor")
    ThreadPoolTaskExecutor pool;

    @Test
    void workerThreadDiffersFromCaller() throws Exception {
        String caller = Thread.currentThread().getName();

        Future<String> future = pool.submit(
                () -> Thread.currentThread().getName());

        String actual = future.get(5, TimeUnit.SECONDS);

        assertNotEquals(caller, actual);
        assertTrue(actual.startsWith("parallel-proof-"));
    }

    @Test
    void twoTasksAreInFlightBeforeRelease() throws Exception {
        OverlapGate gate = new OverlapGate(2);

        CompletableFuture<String> first =
                CompletableFuture.supplyAsync(
                        gate::enterAndAwaitRelease, pool);

        CompletableFuture<String> second =
                CompletableFuture.supplyAsync(
                        gate::enterAndAwaitRelease, pool);

        try {
            assertTrue(
                    gate.awaitAllEntered(Duration.ofSeconds(5)),
                    "Both tasks must reach gate before release");
            assertEquals(2, gate.peakActive());
            assertEquals(2, gate.active());

            // Both are still awaiting release; neither Future is done.
            assertFalse(first.isDone());
            assertFalse(second.isDone());
        } finally {
            gate.open(); // Never leave workers stuck if an assert fails.
        }

        assertTrue(
                first.get(5, TimeUnit.SECONDS)
                        .startsWith("parallel-proof-"));
        assertTrue(
                second.get(5, TimeUnit.SECONDS)
                        .startsWith("parallel-proof-"));

        assertEquals(0, gate.active());
    }

    @Test
    void singleWorkerQueuesSecondTask() throws Exception {
        ThreadPoolTaskExecutor oneWorker =
                new ThreadPoolTaskExecutor();
        oneWorker.setCorePoolSize(1);
        oneWorker.setMaxPoolSize(1);
        oneWorker.setQueueCapacity(1);
        oneWorker.setWaitForTasksToCompleteOnShutdown(true);
        oneWorker.setAwaitTerminationSeconds(10);
        oneWorker.initialize();

        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        AtomicBoolean secondRan = new AtomicBoolean(false);

        try {
            Future<?> first = oneWorker.submit(() -> {
                firstStarted.countDown();
                try {
                    if (!releaseFirst.await(
                            15, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "First task was not released");
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(ex);
                }
            });

            assertTrue(firstStarted.await(5, TimeUnit.SECONDS));

            Future<?> second = oneWorker.submit(
                    () -> secondRan.set(true));

            // Task 1 holds the worker; task 2 is queued.
            assertFalse(secondRan.get());
            assertFalse(second.isDone());

            releaseFirst.countDown();

            first.get(5, TimeUnit.SECONDS);
            second.get(5, TimeUnit.SECONDS);
            assertTrue(secondRan.get());
        } finally {
            releaseFirst.countDown();
            oneWorker.shutdown();
        }
    }

    @Test
    void futureCarriesWorkerException() throws Exception {
        Future<?> future = pool.submit(() -> {
            throw new IllegalArgumentException("worker failure");
        });

        ExecutionException ex = assertThrows(
                ExecutionException.class,
                () -> future.get(5, TimeUnit.SECONDS));

        assertInstanceOf(
                IllegalArgumentException.class, ex.getCause());
        assertEquals(
                "worker failure", ex.getCause().getMessage());
    }

    @Test
    void threadLocalIsNotAutomaticallyPropagated()
            throws Exception {
        ThreadLocal<String> marker = new ThreadLocal<>();
        marker.set("caller-context");

        try {
            assertEquals("caller-context", marker.get());

            Future<String> workerRead = pool.submit(
                    (Callable<String>) marker::get);

            assertNull(workerRead.get(5, TimeUnit.SECONDS));
        } finally {
            marker.remove();
        }
    }

    @Test
    void poolRejectsThirdTaskWhileBothWorkersBlocked()
            throws Exception {
        OverlapGate gate = new OverlapGate(2);

        CompletableFuture<String> first =
                CompletableFuture.supplyAsync(
                        gate::enterAndAwaitRelease, pool);

        CompletableFuture<String> second =
                CompletableFuture.supplyAsync(
                        gate::enterAndAwaitRelease, pool);

        try {
            assertTrue(
                    gate.awaitAllEntered(Duration.ofSeconds(5)));
            assertEquals(2, gate.peakActive());

            // Pool has 2 workers and zero queue capacity.
            assertThrows(
                    TaskRejectedException.class,
                    () -> pool.execute(() -> {
                        throw new IllegalStateException(
                                "Third task must be rejected");
                    }));
        } finally {
            gate.open();
        }

        first.get(5, TimeUnit.SECONDS);
        second.get(5, TimeUnit.SECONDS);
        assertEquals(0, gate.active());
    }
}
~~~

**Exactly 6 JUnit `@Test` methods in the pool class.**

1. **`workerThreadDiffersFromCaller`**: confirms the task runs on another pool thread; compares thread names since the pool has a clear prefix. This tests thread identity, not overlap yet.
2. **`twoTasksAreInFlightBeforeRelease`**: two futures are inside the gate, each having incremented `active`; the test thread observes `active=2`, `peak=2`, and neither future done. This is far stronger proof of **overlap** than sleeping or seeing two log lines.
3. **`singleWorkerQueuesSecondTask`**: a 1-worker pool is held by the first task; the second task sits in `queueCapacity=1` and **has not run** prior to release. This acts as a negative control for worker count limits. `finally` opens the latch and shuts down the pool.
4. **`futureCarriesWorkerException`**: unlike sync `execute`, worker errors arrive via `Future.get()` as `ExecutionException` with the underlying cause. Thus merely watching the `submit` call is not enough to catch task failures.
5. **`threadLocalIsNotAutomaticallyPropagated`**: a `ThreadLocal` set by the test thread does not automatically appear on pool threads. Without `InheritableThreadLocal` or a custom `TaskDecorator`, the sample observes `null`.
6. **`poolRejectsThirdTaskWhileBothWorkersBlocked`**: both workers are busy and queue capacity is 0, so the third task is rejected with `TaskRejectedException`. This is a risk/backpressure behavior that `SyncTaskExecutor` cannot simulate.

**Do not treat rejection as a random framework error.** `ThreadPoolTaskExecutor` has explicit capacity settings; if production uses a large queue, a third task may be enqueued instead of rejected. Tests must match the target production/test configuration. The lesson deliberately picks small capacity to expose the behavior.

**On stability:** Assertions rely on signals (`CountDownLatch`, Futures with deadlines), not "sleep 100 ms so the other thread probably ran". On overloaded CI, a 5-second deadline could still be tight; pick timeouts suited to the environment, but **never use timeouts to create concurrency**. On timeout, the test fails and releases the gate rather than hanging forever.

## 10. JUnit class 3: verifying Spring @Async and self-invocation

**src/test/java/demo/async/AsyncProxyIntegrationTest.java**

~~~java
package demo.async;

import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@Execution(ExecutionMode.SAME_THREAD)
class AsyncProxyIntegrationTest {

    @Autowired
    AsyncProbeService service;

    @Test
    void qualifiedSyncAsyncActuallyRunsOnCallerThread()
            throws Exception {
        String caller = Thread.currentThread().getName();

        CompletableFuture<String> result =
                service.threadFromSyncExecutor();

        assertTrue(result.isDone());
        assertEquals(
                caller, result.get(5, TimeUnit.SECONDS));
    }

    @Test
    void qualifiedParallelAsyncRunsOnPoolThread()
            throws Exception {
        String caller = Thread.currentThread().getName();

        CompletableFuture<String> result =
                service.threadFromPoolExecutor();

        String worker = result.get(5, TimeUnit.SECONDS);

        assertNotEquals(caller, worker);
        assertTrue(worker.startsWith("parallel-proof-"));
    }

    @Test
    void twoProxiedAsyncCallsOverlap()
            throws Exception {
        OverlapGate gate = new OverlapGate(2);

        CompletableFuture<String> first =
                service.waitAtGate(gate);

        CompletableFuture<String> second =
                service.waitAtGate(gate);

        try {
            assertTrue(
                    gate.awaitAllEntered(Duration.ofSeconds(5)));
            assertEquals(2, gate.peakActive());

            assertFalse(first.isDone());
            assertFalse(second.isDone());
        } finally {
            gate.open();
        }

        String worker1 = first.get(5, TimeUnit.SECONDS);
        String worker2 = second.get(5, TimeUnit.SECONDS);

        assertTrue(worker1.startsWith("parallel-proof-"));
        assertTrue(worker2.startsWith("parallel-proof-"));
        assertNotEquals(worker1, worker2);

        assertEquals(0, gate.active());
    }

    @Test
    void selfInvocationBypassesAsyncProxy() throws Exception {
        String caller = Thread.currentThread().getName();

        CompletableFuture<String> result =
                service.selfInvokePoolMethod();

        // Inside selfInvokePoolMethod: this.threadFromPoolExecutor().
        assertTrue(result.isDone());
        assertEquals(
                caller, result.get(5, TimeUnit.SECONDS));
    }
}
~~~

**Exactly 4 `@Test` methods in the `@Async` integration class.**

- The first test uses `@Async("syncProofExecutor")` and proves **the annotation does not force a thread switch** when the selected executor runs inline. An already-completed `CompletableFuture` is the expected consequence.
- The second test uses `@Async("parallelProofExecutor")` and proves invocations **through the Spring proxy** run on a worker thread.
- The third test makes **two `@Async` calls** through the Spring proxy, using a gate to force both workers in-flight before the test releases them. This is the key proof of **real concurrency at the `@Async` boundary** in this project.
- The fourth test proves **self-invocation** bypasses the Spring proxy and executes synchronously. Reading only the annotation on `threadFromPoolExecutor` would mislead you about `this.threadFromPoolExecutor()`.

**Note on fast async tests:** Do not assert `assertFalse(result.isDone())` right after calling `threadFromPoolExecutor()` when it returns almost instantly; it can finish before the caller checks. Only assert not-done in `waitAtGate`, where work has an **explicit waiting point**.

## 11. Test summary and how to run

| Test class | Number of `@Test` | Evidence |
|---|---:|---|
| `SyncTaskExecutorTest` | **6** | Caller thread, inline completion, sequential peak=1, exceptions, nested execute, `ThreadLocal` |
| `ThreadPoolTaskExecutorTest` | **6** | Worker identity, **2 overlapping tasks**, 1-worker queue, `Future` exceptions, `ThreadLocal` isolation, rejection |
| `AsyncProxyIntegrationTest` | **4** | `@Async` sync vs pool, 2 proxied `@Async` tasks overlapping, self-invocation bypass |
| **Total** | **16** | Four complementary proof groups; no `@Disabled` |

**Run command with Gradle Wrapper** (if the project already has wrapper scripts/JAR):

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

If you just created the files in this lesson and **have no Gradle Wrapper yet**, `./gradlew` does not exist. Use a compatible installed Gradle to generate the wrapper or run directly:

~~~bash
gradle test
~~~

Run a single class:

~~~bash
./gradlew test --tests demo.async.SyncTaskExecutorTest
./gradlew test --tests demo.async.ThreadPoolTaskExecutorTest
./gradlew test --tests demo.async.AsyncProxyIntegrationTest
~~~

Test reports usually appear at:

~~~text
build/reports/tests/test/index.html
~~~

**Expected outcome when code/dependencies/lifecycle are sound:** 16 JUnit Jupiter tests are discovered and designed to PASS. The sync class uses a single calling thread; the pool class forces two workers in-flight at a gate; the `@Async` proxy class proves the selected executor directly controls execution. These are **expected outcomes from APIs and assertions**, not a claim that Gradle ran in the reader's environment.

**Important:** The tests prove **two tasks in-flight**, yet still **do not prove** your business algorithm handles every possible interleaving safely. When an application has races over shared state, put the domain operation inside the gated region and assert invariants/DB state after both tasks finish. A two-worker pool is **a precondition to create concurrency**, not proof of business correctness.

### 11.1. When synchronization tests pass yet the application is still broken

Consider an inventory problem with 1 unit remaining. Sequential test:

~~~text
Task A reads stock=1 -> writes stock=0 -> success.
Task B reads stock=0 -> reject.
No oversell error when executed serially.
~~~

In real concurrent execution, an interleaving can happen:

~~~text
Task A reads stock=1 --------------------- updates stock=0
Task B -------- reads stock=1 ----------- updates stock=0
Both report "success" even though only one unit existed.
~~~

**What must be asserted when testing concurrency:** total successful reservations must be `<= initial stock`; no negative stock; no duplicate order IDs; no lost audit events. With JDBC/JPA, check after both `Future`s finish and transactions commit, using an independent query against the test database.

**Do not turn this lesson into exploit crafting.** This is testing correctness of business invariants; production requires transaction isolation, optimistic/pessimistic locking, or atomic SQL updates depending on workload.

## 12. ThreadLocal and test-managed transaction pitfalls

`SyncTaskExecutor` typically lets callbacks **see the caller's `ThreadLocal`s**, as shown in the sixth test. That creates an **architectural discrepancy** compared to a production `ThreadPoolTaskExecutor` dispatching work onto workers:

| Context | `SyncTaskExecutor` from test thread | Pool worker |
|---|---|---|
| Custom `ThreadLocal` | Can see caller's value | Not present automatically |
| Spring default `SecurityContextHolder` | Usually same thread/context | Not propagated automatically |
| MDC log context | May be present | Requires explicit propagation |
| Spring test-managed transaction | Can share transaction bound to caller | Does not join caller's transaction |
| Locale/request context | May linger on caller thread | May be null or wrong if undesigned |
| Error stack/exception | Direct `execute` can throw at caller | Typically observed via `Future`/handler |

A test annotated with Spring TestContext `@Transactional` that replaces all async work with `SyncTaskExecutor` makes database writes **join the test's transaction** and roll back. Yet production HTTP server threads and async pools do not carry the caller's test transaction. Thus the same test can look "green with a clean DB" under a sync executor while committing independent rows in real async execution.

**Critical distinction:** A worker thread **can** open its **own** transaction if its code crosses a Spring `@Transactional` proxy or `TransactionTemplate`. The accurate statement is: it **does not inherit the caller's test transaction**, not "workers never have transactions".

If async code needs `SecurityContext`, use Spring Security's `DelegatingSecurityContextAsyncTaskExecutor` or an appropriate `TaskDecorator`, **never forwarding raw JDBC Connections or `TransactionStatus` across threads**. Transaction resources have thread-bound lifecycles and are often not thread-safe. When testing propagation, verify **presence**, **right user/tenant**, and **cleanup** so a previous request's context never leaks into the next.

### 12.1. Counter-example: fake async giving false positives on transactions

~~~java
@Test
@Transactional
void wrongProofOfAsyncRollback() {
    // The code below only illustrates the mistake.
    // If the async executor was swapped for SyncTaskExecutor:
    service.performAsyncWrite();

    // End-of-test rollback may clean the write because the callback
    // ran right on the test thread.
    // This does NOT prove rollback when a real worker processes it.
}
~~~

This is a **counter-example snippet**, not part of the runnable source in Sections 7–10; the main project has no `DataSource`. When tests must verify async DB work, use a **disposable database**, a real async executor, wait for the `Future` to finish, and query state after commit/rollback. Never annotate the test client with `@Transactional` and assume side effects on other threads roll back automatically.

## 13. `@Scheduled` is a separate scheduling problem

`@Async` **submits work** to an executor; `@Scheduled` **triggers** methods on a fixed rate, fixed delay, or cron. Schedulers are typically driven by a **`TaskScheduler`**, such as `ThreadPoolTaskScheduler`, not the `TaskExecutor` picked for an `@Async` method.

Therefore replacing `TaskExecutor` with `SyncTaskExecutor` in tests **does not prove**:
- Cron expressions actually fire at intended times.
- Whether `fixedRate` triggers overlap.
- Whether `fixedDelay` waits for previous completion as expected.
- Whether the scheduler has enough pool threads for two scheduled jobs to overlap.
- Whether one stalled job starves another job.
- Whether misfires, clock skew, DST, and scheduling jitter are handled.

Example scheduler config (standalone snippet, not in the runnable project):

~~~java
@Bean
ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler =
            new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(2);
    scheduler.setThreadNamePrefix("schedule-test-");
    return scheduler;
}
~~~

To **prove scheduling overlap**, genuinely trigger two scheduled executions (or the same business handler triggered via the scheduler) and observe them with a gate inside the work region. A test calling an `@Scheduled` method directly bypasses the scheduling trigger and proves nothing about cron/`fixedRate` semantics.

**Another nuance:** If a method has both `@Scheduled` and `@Async`, the scheduler calls the proxy method while the chosen async executor governs actual work execution. Job overlap then depends on **both scheduler triggers and async executor capacity**. Using a sync executor for `@Async` forces the scheduler thread to wait until the method ends, potentially hiding real overlap present in production.

### 13.1. Two-tier schedule testing

**Tier 1 — job logic:** Separate business logic from annotations/triggers, test method logic sequentially or with a fake `Clock` when needed. Never wait on a real clock to reach a cron time.

**Tier 2 — triggers/concurrency:** Use a real scheduler on test-controlled timing, wait on `CountDownLatch`/observer events, verify trigger counts, confirm zero unintended overlaps (or expected overlaps per contract), and clean up scheduled tasks afterward. In multi-replica distributed deployments, a single local scheduler pool test **does not prove a cluster-wide singleton job**; you need distributed locks/leases/idempotency and matching integration tests.

**Clock/virtual time:** Injected/fake `Clock` helps test time-dependent domain logic, yet does not advance Spring's real scheduler through fake time. For cron, DST, or timer tests, pick an abstraction supporting virtual time or test pure schedule calculations separately.

## 14. How do TaskExecutor, ExecutorService, and CompletableFuture differ?

Spring `TaskExecutor` extends `java.util.concurrent.Executor`. `SyncTaskExecutor` only provides `execute(Runnable)`, so it is **not a thread pool** and does not expose `submit(Callable)` directly like `ExecutorService`. Spring `ThreadPoolTaskExecutor` implements `AsyncTaskExecutor`, supporting `submit` and `Future`.

`CompletableFuture` has several usage patterns easily misunderstood:

~~~java
CompletableFuture<String> ready =
        CompletableFuture.completedFuture("ok");
// Already finished; creates zero extra concurrency.

CompletableFuture<String> inPool =
        CompletableFuture.supplyAsync(
                () -> Thread.currentThread().getName(),
                parallelExecutor);
// Work is submitted to the specified executor.
~~~

This snippet uses `parallelExecutor` representing a configured `Executor`. Using `completedFuture` alone spawns no worker; `supplyAsync` with an explicit executor submits the callback there. Calling `supplyAsync(supplier)` without an executor normally uses the ForkJoin common pool, unrelated to the Spring Boot `TaskExecutor` under test.

**`thenApply` vs `thenApplyAsync`:** A `thenApply` callback may run on the thread completing the previous stage (or the attaching thread if already completed), guaranteeing no thread hop. `thenApplyAsync` dispatches the callback asynchronously to an executor (common pool or explicit executor). When testing context propagation or concurrency, verify **which exact thread runs the callback**, rather than guessing from the `Future` name.

**Exceptions:** Direct `SyncTaskExecutor.execute` can throw immediately, whereas `ThreadPoolTaskExecutor.submit` returns a `Future` and exceptions surface on `Future.get()`. With `CompletableFuture`, failures are observed via `get`, `join`, `handle`, `whenComplete`, or `exceptionally`; merely submitting and asserting state can miss a failed task.

**Cancellation:** `future.cancel(true)` is normally an interruption request, not a guarantee that side effects stopped or rolled back. Tasks ignoring interrupts can keep running; use finite timeouts and `finally` cleanup. Never carelessly use `assertTimeoutPreemptively` in transactional integration tests: the callback may run on another thread and escape test rollback.

## 15. Designing a real concurrency test for a business invariant

Follow three phases:

**Phase A — Arrange:**
- Seed fixed initial business state (e.g., `inventory=1`).
- Prepare **2 separate requests/tasks** acting on the same object key.
- Configure an executor with enough workers and a gate.
- Keep instrumentation decoupled from business code so recording `AtomicInteger peakActive` **does not accidentally serialize the business path** under test.

**Phase B — Force concurrent interleaving:**
- Bring both workers into the **contention zone**, such as right after reading the same version/inventory or before updating.
- Await both arrivals; release the gate.
- When you genuinely must test "both read the same stale value", place the barrier **after read, before write** using a test-only hook or controllable dependency; placing a barrier at method entry only proves two tasks started close together, **without forcing** the dangerous interleaving.
- Never use sleeps or thread priorities hoping to trigger a race.

**Phase C — Assert invariants after completion:**
- Call `Future.get(timeout)` on both; classify success/conflict per contract.
- Query the DB after transactions finish using a fresh connection/transaction if needed.
- Assert **no oversell**, **no duplicates**, **no lost updates**, and **side-effect counts match accepted operations**.
- Test failure paths and cleanup, including when one `Future` throws an exception.
- Repeat across multiple seeds or workload scenarios to widen coverage; **one passing interleaving does not prove every interleaving is safe**.

Pseudocode example of **post-completion** assertions:

~~~java
// Snippet: repository and business operations belong to the real system.
Result first = future1.get(5, TimeUnit.SECONDS);
Result second = future2.get(5, TimeUnit.SECONDS);

long accepted = Stream.of(first, second)
        .filter(Result::accepted)
        .count();

assertEquals(1L, accepted);
assertEquals(0, inventoryRepository.available("SKU-1"));
assertEquals(1L, reservationRepository.countBySku("SKU-1"));
~~~

This is a **non-standalone snippet**; `Result`, `inventoryRepository`, and `reservationRepository` are undefined here. It illustrates asserting the **true business invariant**, not merely peak in-flight count. If policy permits two tasks drawing from stock of 2 units, adjust the expected accepted count accordingly.

### 15.1. Atomic increments in instrumentation do not fix lost updates

~~~java
AtomicInteger tracked = new AtomicInteger();
tracked.incrementAndGet();
~~~

`tracked` is safe because of atomic operations, yet if production code does:

~~~java
int balance = account.getBalance();
account.setBalance(balance - amount);
~~~

two threads can still read the same stale balance and overwrite each other. Never mistake an atomic test counter for real transaction/locking in business code. For DBs, evaluate optimistic version fields (`@Version`), atomic conditional `UPDATE`s, serializable transactions, or pessimistic row locks per workload.

### 15.2. Overlap tests are not stress tests

A latch-gated test exercises one specific schedule deterministically and is great for regressions. For higher confidence against complex races, you may need:
- Varied interleavings, controlled random yields/delay injection, or property-based scenarios.
- Stress/integration tests in production-like environments (DB, pools, CPU quotas, thread counts).
- **`jcstress`** for pure-JVM Java Memory Model / visibility / linearizability issues.
- Load tests/benchmarks for throughput and queuing latency (never use unit test elapsed time as a production KPI).
- Fault injection at transaction commits, message delivery, interruption, and shutdown.
- Observability into active threads, queue depth, rejected tasks, and downstream failures.

No single assertion can "prove race freedom" across every execution of an arbitrary system. Identify the exact behavior you need to prove, then pick the matching technique.

## 16. Mistakes and troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `@Async` test returns immediately yet always uses same thread | Selected executor is `SyncTaskExecutor` or self-invocation | Check qualifier, proxy, and thread identity |
| 2 `execute` calls yet `peakActive=1` | Sync executor runs serially or pool has only 1 worker | Pool with `>=2` workers and gate |
| Test hangs at initial latch | Caller blocked inside `SyncTaskExecutor` before second submit | Never use a 2-party gate with sequential inline submits |
| Test using `Thread.sleep(50)` fails occasionally | Non-deterministic scheduling/CI | `CountDownLatch`/`CyclicBarrier` and bounded waits |
| `@Async` test flips between `isDone=true` and `false` | Task runs too fast | Use a gate when proving pending state |
| Passes with sync executor yet DB leaks on deploy | Test's thread-local transaction didn't propagate to workers | Use real async executor and DB isolation tests |
| Principal/MDC exists in test yet null on worker | `SyncTaskExecutor` hid missing context propagation | Test real worker, proper propagator, cleanup |
| `@PreAuthorize`/`@Async` skipped on internal calls | Self-invocation bypassed proxy | Extract bean / call through proxy |
| Switching `SyncTaskExecutor` to pool breaks exception test | Exceptions now travel through `Future` instead of caller | Call `get()/join()` and assert cause |
| `TaskRejectedException` on third submission | 2-worker pool, queue capacity 0 | Backpressure policy; test retry/reject/handling |
| Pool keeps tasks after test | Gate unreleased or `Future` unawaited | `finally gate.open()` and bounded `get`/shutdown |
| Pool always runs only 1 thread | Core size 1 + large queue, tasks get queued | Raise core size / adjust queue for test |
| `.setMaxPoolSize(8)` still shows only 1 thread | Core=1, queue has room so pool hasn't scaled to max | Understand core/queue interaction |
| Test passes yet business loses updates | Only asserted `peak=2`, didn't assert post-interleaving invariants | Place barrier near shared state, assert DB |
| Test checks `ThreadLocal` using `InheritableThreadLocal` | Inheritance behavior differs | Test the actual `ThreadLocal` type used |
| `NoUniqueBeanDefinitionException` for `Executor` | Multiple `Executor` beans without clear qualifier/default | `@Async("beanName")` or `AsyncConfigurer` |
| `@Scheduled` works in direct call yet misses cron | Direct call bypasses scheduler | Separate `TaskScheduler`/trigger integration test |
| 1-thread scheduler pool hogged by long job | Too few scheduler threads; unrelated to `SyncTaskExecutor` | Size scheduler pool, bound tasks |
| Cannot run Gradle tests | Missing wrapper, wrong Java 17 version | Generate wrapper / match toolchain |
| Test times out under heavy CI load | Too-tight deadline, uninitialized/contended pool | Check JUnit parallelism, pool bean, size timeout reasonably |
| App relies on virtual threads yet tested on Java 17 | Virtual threads require Java 21+ | Separate versions/scenarios, don't extrapolate from Java 17 |
| `.get()` hangs forever | Task deadlock / future never completes | Bounded `get` and release/cancellation |
| `@Transactional` on worker "has no effect" | Call bypassed tx proxy or wrong tx context | Test boundaries/propagation, don't copy JDBC context |

### 16.1. Checklist when an async test is suspected of a "false pass"

1. **Read the real name of the executor bean** injected/selected by `@Async`. Is it using `SyncTaskExecutor`?
2. If `SyncTaskExecutor`, clarify whether the test only proves **sequential behavior** or wrongly claims concurrency.
3. Does the test go through a **Spring proxy**? Is there self-invocation or manual `new Service()`?
4. Does the test have two real worker threads or two independent calling threads?
5. Is there a **gate/barrier** guaranteeing two tasks are in-flight simultaneously before release?
6. Does the gate use bounded awaits and `finally` release?
7. Does the test check both `Future` completion and exceptions (`get`/`join`)?
8. Does `peakActive` actually measure the critical section under test, or just method entry?
9. Does the test assert business invariants/DB outcomes after both tasks complete?
10. Are `ThreadLocal`/`SecurityContext`/transaction contexts assumed to propagate automatically?
11. Are pool capacity, queue/rejection policies, and zero parallel-test interference verified?
12. For `@Scheduled`, are **scheduler triggers** tested rather than only manual method calls?
13. When moving tests from sync to async, are fixtures/databases properly isolated and cleaned up?
14. Could threads/connections/resources leak on timeout or failure?
15. Are code review claims properly scoped: "observed overlap in this test", not "proven thread-safe everywhere"?

## 17. Practice questions

**Exercise 1 — Thread identity.** With `SyncTaskExecutor`, inspect `Thread.currentThread()` before and inside `execute`. Why is it the same thread? If two independent caller threads share one executor, can overlap occur?

**Exercise 2 — Ordering.** Run two tasks with a sync executor; log `[A-start,A-end,B-start,B-end]`. Switch to a 2-worker pool with a gate. Is log order still fixed? Which assertions should you avoid?

**Exercise 3 — Exceptions.** Have a callback throw `IllegalArgumentException`. With direct `SyncTaskExecutor.execute`, where does the exception surface? With `ThreadPoolTaskExecutor.submit`, what must the test call to see the error?

**Exercise 4 — Latch.** Put `CountDownLatch(2)` in two tasks yet submit through a single-thread sync executor. Why does the test hang/time out? Is that a business bug or a test synchronization bug?

**Exercise 5 — Pool capacity.** Change `corePoolSize=2` to 1, `queueCapacity=1`. Why can't the second task overlap even with `maxPoolSize=2`? What is the difference between core, max, and queue?

**Exercise 6 — No sleep.** Write a concurrency test without `Thread.sleep`, using only `CountDownLatch`, `AtomicInteger peakActive`, and bounded `Future.get`.

**Exercise 7 — `@Async` qualifier.** Switch `@Async("parallelProofExecutor")` to `@Async("syncProofExecutor")`. Which test fails? Why doesn't `@Async` spawn a thread when the executor runs inline?

**Exercise 8 — Self-invocation.** Remove `selfInvocationBypassesAsyncProxy` and add an internal call inside the service. In real production, does `@Async` apply? How do you fix the architecture?

**Exercise 9 — `ThreadLocal`.** Set a `ThreadLocal` on the test caller, read it inside the sync task and the pool task. When should context propagate, and when should it fail closed? Never copy JDBC transaction resources across threads.

**Exercise 10 — Timeouts.** Have a task ignore interrupts and call `Future.cancel(true)`. What can happen? How do you clean up without mistaking timeouts for rollbacks?

**Exercise 11 — Lost updates.** Two clients concurrently reserve `SKU-1` with 1 unit left. Place a gate **after read, before write** to force the race. Design an atomic `UPDATE`/optimistic lock and re-test.

**Exercise 12 — `CompletableFuture`.** Compare `completedFuture`, `supplyAsync` with an explicit executor, `thenApply`, and `thenApplyAsync`. Which methods prove a thread hop?

**Exercise 13 — `@Scheduled`.** Write a fixed-rate job and another scheduled job. Use a real `TaskScheduler` with an appropriate pool; verify overlap/no-overlap per contract. Why isn't swapping `TaskExecutor` to sync enough?

**Exercise 14 — Scheduler drift.** Add work taking longer than the period and observe schedules on 1-thread vs 2-thread schedulers. Verify true `fixedRate`/`fixedDelay` semantics instead of guessing from logs.

**Exercise 15 — DB transactions.** An `@Transactional` test calls an `@Async` service first with `SyncTaskExecutor` and then with `ThreadPoolTaskExecutor`. Explain why rollback and `ThreadLocal` differ; test against a disposable DB to avoid polluting data.

**Exercise 16 — Stress.** Create a 1,000-task test comparing throughput, rejected tasks, and queue depth. Why shouldn't those numbers be used as official benchmarks if run on a noisy test runner?

**Exercise 17 — Virtual threads.** If upgrading to JDK 21 and `SimpleAsyncTaskExecutor` in virtual-thread mode, tasks can still overlap yet resource constraints differ. Which assertions stay valid? Which assumptions about thread names/pool reuse must change?

**Exercise 18 — Review.** Audit existing tests using `SyncTaskExecutor`, `Runnable::run`, `MoreExecutors.directExecutor`, or fake synchronous executors; separate tests needing only deterministic logic from those claiming "thread-safety".

## 18. Official references

- [Spring Framework 6.1 — SyncTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/task/SyncTaskExecutor.html): runs each task synchronously on the calling thread, primarily useful for testing.
- [Spring Framework 6.1 — ThreadPoolTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): core/max pool, `queueCapacity`, `Future`, lifecycle, and rejection.
- [Spring Framework 6.1 — TaskExecutorAdapter API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/task/support/TaskExecutorAdapter.html): adapts `Executor` to `AsyncTaskExecutor`.
- [Spring Framework 6.1 — @EnableAsync API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html): async proxies, executor selection, and `AsyncConfigurer`.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Async`, executor qualifiers, schedulers, and exceptions.
- [Spring Boot 3.3 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html): `applicationTaskExecutor`, auto-configuration, and scheduler settings.
- [Java 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): awaited signals and happens-before guarantees.
- [Java 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): completion, executor selection, errors, and cancellation.
- [Java 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): core/max threads, work queues, and rejection.
- [Java 17 — AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): thread-safe atomic counters for test instrumentation.
- [Spring Framework — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): transaction `ThreadLocal` and risks when tests run on other threads.
- [OpenJDK jcstress](https://openjdk.org/projects/code-tools/jcstress/): specialized stress tests for Java Memory Model / concurrency semantics.

**Final takeaway:** `SyncTaskExecutor` is **not wrong**: it excels when testing logic/callbacks in deterministic order without switching threads. However, two sequential submissions through this executor **do not prove** two tasks can overlap, miss many race conditions, and can mask `ThreadLocal`/transaction context bugs of real async execution. When the requirement is **"proving concurrent behavior"**, pick a real executor with enough workers, **use latches/barriers to force simultaneous in-flight execution, release in `finally`, await bounded `Future`s, and assert business invariants after completion**. Separate scheduling tests from work logic tests; distinguish `@Async` proxies from self-invocation; and never infer from a single overlap test that the system is safe across all interleavings.