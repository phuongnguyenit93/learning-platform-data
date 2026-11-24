# Timeout, Task Cancellation, and Thread Cleanup After Tests in Spring Boot

## 1. The problem: test PASSES yet threads keep running

In Spring Boot, `@Async`, `@Scheduled`, `TaskExecutor`, and `TaskScheduler` offload work from the calling thread. These same features are frequent culprits behind hung integration tests, data leaks, and test-order dependencies:

- A test calls `Future.get(100, MILLISECONDS)`, receives `TimeoutException`, yet the worker keeps writing to the database.
- A test calls `Future.cancel(true)`, sees `isCancelled()==true`, and assumes the task exited.
- `CompletableFuture.cancel(true)` marks the completion stage cancelled without interrupting the underlying worker.
- A scheduler runs in the background while another test swaps fixtures or mocks.
- A test creates an `ExecutorService`/`ThreadPoolTaskScheduler` without shutting it down, preventing the JVM from exiting.
- `@Async void` throws an exception on a worker, unseen by the test thread so the test still PASSES.
- `@SpringBootTest @Transactional` is mistakenly expected to roll back every side effect produced by async threads.
- `assertTimeoutPreemptively` moves the body onto a thread different from the one Spring TestContext bound the transaction to.

Three things must be distinguished because they **cannot substitute for one another**:

1. **Timeout:** bounds how long a caller waits for a result.
2. **Cancellation:** requests cancelling a task, potentially requesting interruption of a running worker.
3. **Cleanup:** verifies the worker actually left the task body and test-owned threads/resources were released.

**Never conclude "timeout = cancel = task stopped".**

### After this lesson, you can

- Use `Future.get(timeout)`, `CompletableFuture.orTimeout`, and JUnit `assertTimeout` deliberately.
- Understand `cancel(false)`, `cancel(true)`, `isDone()`, `isCancelled()`, and `InterruptedException`.
- Write tasks that respond to interruption without leaking resources when tests fail.
- Synchronize tests with `CountDownLatch` instead of `Thread.sleep`.
- Verify `@Async` through the Spring proxy and the right thread pool.
- Prevent `@Scheduled` from ticking randomly in test contexts while still testing business logic.
- Cancel `ScheduledFuture` handles and shut down test-owned schedulers.
- Clean up test-owned executors with `shutdown`/`awaitTermination` without breaking Spring-managed executor beans.
- Distinguish lifecycles, `ThreadLocal` transactions/security, HTTP/DB timeouts, and virtual threads.
- Design repeatable suites independent of wall-clock time or test ordering.

## 2. Four entities of an asynchronous job

~~~text
JUnit test thread                      Worker thread
-----------------                     -------------------
submit(Callable) --------------------> ExecutorService
       |                                       |
       v                                       v
 Future<String>                          Callable.call()
       |                                       |
       +-- get(timeout) --> result?            +-- block / I/O / compute
       |          |                            |
       |          +--> TimeoutException        |
       |                    |                  |
       |                    +-- worker MAY STILL RUN
       |
       +-- cancel(true) ----------------> interrupt request
       |                                     |
       |                              task cooperates to exit
       |
       +-- latch.finished.await(timeout)
             |
             +-- confirms worker passed finally
~~~

- `TaskExecutor`/`AsyncTaskExecutor` represents where a task runs.
- `TaskScheduler` registers when/how work runs: one-shot, fixed rate, fixed delay, cron.
- `Future` is a handle to wait for results/cancel; it is not proof that a thread has died.
- `ThreadPoolTaskExecutor` is Spring's wrapper around a worker pool with a Spring lifecycle.
- `ThreadPoolTaskScheduler` wraps a scheduled executor, typically managing its own threads and shutdown.
- `@Async`/`@Scheduled` require annotation processing and context; invoking methods directly does not activate framework behavior.

### 2.1 Semantics matrix

| Action | Effect | What must NOT be inferred |
| --- | --- | --- |
| `Future.get(200, MILLISECONDS)` | Caller waits at most 200ms | Task automatically cancelled after 200ms |
| `Future.cancel(false)` | Cancels if possible; does not interrupt running task | Running worker has exited |
| `Future.cancel(true)` | Requests interrupting running worker | Worker definitely stopped |
| `CompletableFuture.cancel(true)` | Completion stage ends with `CancellationException` | Physical computation was interrupted |
| `ScheduledFuture.cancel(true)` | Cancels schedule, attempts to interrupt running task | Scheduler pool was shut down |
| `ExecutorService.shutdown()` | Rejects new tasks, runs already-submitted tasks | Already waited for workers to terminate |
| `ExecutorService.shutdownNow()` | Attempts to interrupt active tasks, returns queued tasks | Forced every task to exit |
| `awaitTermination(timeout)` | Waits after shutdown was initiated | Triggers shutdown on its own |
| `@Async` returning `CompletableFuture` | Caller receives a completion stage | Underlying future is always interruptible |
| `@Scheduled` method called directly | Runs method body | Cron trigger was tested |
| `assertTimeoutPreemptively` | Enforces preemptive bound on assertion | No lingering side effects on other threads |

## 3. Timeout: stopping the wait does not mean stopping the task

### 3.1 Future.get(timeout)

~~~java
Future<String> future = executor.submit(this::loadSlowly);

try {
    return future.get(300, TimeUnit.MILLISECONDS);
} catch (TimeoutException ex) {
    future.cancel(true);
    throw new IllegalStateException("Timed out", ex);
}
~~~

This is an **illustrative fragment**, not a standalone file; it requires `executor` and `loadSlowly`. `get(timeout)` simply throws if the result is absent after the deadline; **it does not auto-cancel**. Calling `cancel` is a **separate policy**, and `cancel(true)` only requests interruption.

Do not write:

~~~java
assertThrows(TimeoutException.class,
        () -> future.get(100, TimeUnit.MILLISECONDS));
// Concluding "the worker stopped" is wrong.
~~~

### 3.2 CompletableFuture.orTimeout and completeOnTimeout

Java 17:

~~~java
stage.orTimeout(200, TimeUnit.MILLISECONDS);
stage.completeOnTimeout("fallback", 200, TimeUnit.MILLISECONDS);
~~~

Both operations complete the stage at the deadline (with an exception or fallback). However, an underlying physical HTTP/DB/background computation **may keep running**. If you need to stop the physical task, keep the cancellation handle at the execution layer and configure separate I/O timeouts and resource closing.

### 3.3 HTTP timeout, task timeout, and overall deadline

~~~text
Logical request deadline: 2s
    |
    +-- worker queue waiting
    +-- HTTP connect timeout: 1s
    +-- HTTP read timeout: 1s
    +-- retry backoff
    +-- DB commit or rollback
    +-- cleanup / compensation
~~~

Cumulative durations can exceed the request deadline. Spring `@Async` does not automatically configure HTTP, database statement, or transaction timeouts. Bound each resource via its own API, then monitor total latency.

### 3.4 JUnit assertTimeout and assertTimeoutPreemptively

~~~java
assertTimeout(Duration.ofSeconds(2),
        () -> service.compute());

assertTimeoutPreemptively(Duration.ofSeconds(2),
        () -> service.compute());
~~~

These are two **illustrative patterns**. `assertTimeout` normally runs on the **caller thread**, measuring elapsed time without forcibly aborting a forever-blocked method. `assertTimeoutPreemptively` may run the body on **another thread**. Spring TestContext warns this can break test-managed transactions bound to the test thread; database writes inside the body can commit independently instead of rolling back with the test. `SecurityContext`/MDC/tenant `ThreadLocal`s can also be lost.

Do not substitute preemptive test timeouts for real HTTP/DB/worker deadlines.

## 4. Future.cancel(false), cancel(true), and cooperative interruption

JDK `Future.cancel(boolean mayInterruptIfRunning)`:

- If the task has not started yet, cancellation can prevent it from running.
- If already running, `cancel(false)` normally does not interrupt the worker; the task may run to completion even though the `Future` reports cancelled.
- `cancel(true)` requests interrupting the thread executing the task if the implementation tracks the worker.
- The worker may fail to respond to interrupts, e.g., CPU loops ignoring the flag or I/O drivers without interrupt support.
- `Future.isDone()` can be true due to completion, failure, or cancellation.
- `Future.get()` after cancellation typically throws `CancellationException` instead of returning any value the task computed later.

### 4.1 Tasks must cooperate

~~~java
try {
    releaseLatch.await();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
} finally {
    closeResources();
}
~~~

This fragment requires a real `releaseLatch` and `closeResources`. In CPU-bound tasks, check `Thread.currentThread().isInterrupted()` periodically. Tasks waiting on `CountDownLatch.await()` throw `InterruptedException` upon interrupt, which is convenient to test.

**Never use `Thread.stop()`.** Cancellation must be designed so tasks exit safely, release locks/connections/streams in `finally`, and avoid leaving corrupted data.

### 4.2 Why is checking isCancelled alone not enough?

~~~text
Future.cancel(true) returned true
Future.isCancelled() == true
Future.isDone() == true

Yet the task may still be:
- writing to database,
- calling HTTP,
- holding a file lock,
- waiting on I/O,
- running a loop without checking interrupt.
~~~

Tests need an independent signal from the **end of the task body**, such as `finished.countDown()` in `finally`. When the test owns the executor too, also check `awaitTermination`.

## 5. CompletableFuture cancellation differs from FutureTask

Per the Java 17 Javadoc, `CompletableFuture.cancel(boolean)` is equivalent to exceptional completion; the `mayInterruptIfRunning` argument **does not interrupt the worker** in this implementation.

~~~java
CompletableFuture<String> visible = new CompletableFuture<>();

Future<?> physical = executor.submit(() -> {
    String result = doBlockingWork();
    visible.complete(result);
});

visible.cancel(true);      // Does not automatically interrupt physical worker.
physical.cancel(true);     // This is the actual task cancellation attempt.
~~~

This is a fragment. Do not equate `CompletableFuture.cancel(true)` with `FutureTask.cancel(true)`. With Spring `@Async`, proxy/executor wrapping can affect cancellation details; check the exact version and APIs your application uses.

### 5.1 Cancelled result and running computation can coexist

Even after the stage is cancelled, the worker may reach `visible.complete(value)`; calling `complete` leaves the cancelled stage unchanged, yet **side effects** executed by the worker may still occur. Therefore:
- An API returning a fallback on timeout does not guarantee the database won't still commit.
- "Task canceled" is not equivalent to "task body entered `finally`".
- Use a cancellation token or physical `Future` to stop actual computation.

## 6. @Async in Spring Boot

Requires `@EnableAsync`, a Spring-managed bean, and calling the method **through the proxy**. `@Async("workExecutor")` names the target pool.

~~~java
@Service
public class AsyncService {
    @Async("workExecutor")
    public CompletableFuture<String> compute() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName());
    }
}
~~~

This is a snippet; the complete demo is in Section 11.

**Self-invocation:**

~~~java
public String outer() {
    return this.compute().join(); // Normally bypasses the proxy.
}
~~~

If the same bean calls its own `@Async` method, proxy-based interception may be bypassed and the task runs on the caller thread. Move the worker into a separate bean or use a programmatic executor.

### 6.1 @Async void exception

A method:

~~~java
@Async("workExecutor")
public void send() {
    throw new IllegalStateException("send failed");
}
~~~

has no `Future` for the caller to `get()` the exception. Spring may log it or route it to `AsyncUncaughtExceptionHandler`. If a test only calls `send()` and returns, it can PASS even when the worker failed; inject an exception handler/test probe or change the contract to `Future`/`CompletableFuture` so callers can observe outcomes.

### 6.2 Boot auto-configured executor

Spring Boot 3.5 can auto-configure `AsyncTaskExecutor` or use custom `Executor` beans. `@Async("workExecutor")` selects the right pool when multiple beans exist, avoiding mix-ups between MVC async/GraphQL/WebFlux executors and application jobs. Do not guess the default bean from method names alone.

## 7. @Scheduled, fixedRate, fixedDelay, and cron in tests

`@EnableScheduling` tells Spring to register `@Scheduled` methods at context startup. Without test isolation, jobs can run mid-assertion and mutate fixtures.

| Type | Meaning | What tests should do |
| --- | --- | --- |
| `fixedRate` | Interval between start points, per scheduler | Test triggers separately, avoid arbitrary sleeps |
| `fixedDelay` | Interval after previous run finishes | Extract business body into a service |
| `cron` | By calendar expression and timezone | Check `CronExpression`/`Trigger` with a clock |
| `schedule(task, Instant)` | Once at a given instant | Cancel handle before start when needed |
| `scheduleAtFixedRate` | Repeatedly, returning `ScheduledFuture` | Cancel and shut down explicitly |
| Quartz/distributed scheduling | Persistence/multi-node | Test locks/misfires/idempotency separately |

### 7.1 Disabling cron intentionally in ordinary tests

Spring `@Scheduled` accepts `"-"` (`CRON_DISABLED`) to disable cron:

~~~java
@Scheduled(cron = "${demo.maintenance.cron:-}")
public void runOnce() {
    // business logic
}
~~~

With test property:

~~~properties
demo.maintenance.cron=-
~~~

The test gets no auto-running trigger. Production can configure a real cron:

~~~properties
demo.maintenance.cron=0 0 3 * * *
~~~

In the Spring property placeholder above, the default value for `demo.maintenance.cron` is `-`. Never turn fixed-rate into 1ms just to test with `Thread.sleep`.

### 7.2 Testing the body vs testing scheduling wiring

- Call the service method directly to test logic.
- Test cron/triggers using `CronExpression` and controlled `Clock`/`Instant` when timing SLAs exist.
- Test a scheduled handle using a local `TaskScheduler` in JUnit and cancel it afterward.
- With multiple app replicas, `@Scheduled` fires **on every instance**; use distributed locks or idempotency to prevent duplicate job execution.

## 8. ThreadPoolTaskExecutor and lifecycle ownership

### 8.1 Spring-managed bean

~~~java
@Autowired
@Qualifier("workExecutor")
ThreadPoolTaskExecutor workExecutor;
~~~

This pool may reside in Spring TestContext's **cached `ApplicationContext`**. Do not call `workExecutor.shutdown()` inside `@AfterEach` to "clean up threads": later test classes reusing that bean will receive `TaskRejectedException`.

**Proper approach:** clean up/cancel/release **the test's own tasks** and await `finished`; let Spring close the executor when the context actually closes. If you need to test shutdown lifecycles, instantiate a **test-owned** executor.

### 8.2 Test-owned ExecutorService

~~~java
ExecutorService owned = Executors.newSingleThreadExecutor();
try {
    // tests and assertions
} finally {
    owned.shutdownNow();
    if (!owned.awaitTermination(3, TimeUnit.SECONDS)) {
        throw new AssertionError("Owned threads not terminated");
    }
}
~~~

This is a fragment; it can throw `InterruptedException`, which must be handled appropriately. `shutdownNow()` is best effort; `awaitTermination==false` signals incomplete cleanup.

### 8.3 Spring shutdown flags

| Option | Effect |
| --- | --- |
| `setWaitForTasksToCompleteOnShutdown(false)` | Early shutdown, may interrupt active tasks and drop queued ones |
| `setWaitForTasksToCompleteOnShutdown(true)` | Allows existing/queued tasks to run to completion |
| `setAwaitTerminationSeconds(n)` | Waits at most `n` seconds during Spring executor shutdown |
| `setStrictEarlyShutdown(true)` | Signals early shutdown when the context closes |
| `setThreadNamePrefix(...)` | Makes threads easy to spot in logs/thread dumps |
| `setCorePoolSize`/`setMaxPoolSize` | Controls concurrency |
| `setQueueCapacity` | Bounds queue size, avoiding unbounded resource growth |

If wait-for-completion is true and a task hangs, shutdown can stall or fail to finish even with a wait timeout. Tasks need cancellation/deadlines before shutdown.

## 9. ThreadPoolTaskScheduler lifecycle

`ThreadPoolTaskScheduler` exposes `schedule`, `scheduleAtFixedRate`, `scheduleWithFixedDelay`, and `ScheduledFuture<?>` for cancellation.

~~~java
ThreadPoolTaskScheduler scheduler =
        new ThreadPoolTaskScheduler();
scheduler.setPoolSize(1);
scheduler.setRemoveOnCancelPolicy(true);
scheduler.initialize();

try {
    ScheduledFuture<?> handle = scheduler.schedule(
            () -> perform(),
            Instant.now().plus(Duration.ofHours(1)));
    handle.cancel(false);
} finally {
    scheduler.shutdown();
    scheduler.getScheduledThreadPoolExecutor()
            .awaitTermination(3, TimeUnit.SECONDS);
}
~~~

This is a fragment (requires `perform`). `setRemoveOnCancelPolicy(true)` purges cancelled delayed tasks from the queue faster; it does **not** mean it interrupts running workers. Cancelling a `ScheduledFuture` only cancels **that specific schedule/task**, not the scheduler pool.

For a Spring-managed `ThreadPoolTaskScheduler` bean, also avoid shutting it down in regular `@AfterEach` because the context may still use it.

## 10. Java 17+ / Spring Boot 3.5.x project

This hands-on suite needs no database, external API, Docker, or waiting on cron clocks. There are **12 JUnit Jupiter methods** across three test classes:

1. `AsyncIntegrationTest`: Spring `@Async`, Future timeout/cancel, `CompletableFuture` cancel, disabled cron.
2. `TaskSchedulerCancellationTest`: cancel delayed/periodic jobs, verify scheduler terminated.
3. `OwnedExecutorLifecycleTest`: graceful shutdown and interrupting shutdown.

Structure:

~~~text
async-test-demo/
  settings.gradle
  build.gradle
  src/main/java/example/async/
    AsyncDemoApplication.java
    ExecutorConfig.java
    AsyncWorker.java
    ScheduledMaintenance.java
  src/test/java/example/async/
    BlockingJob.java
    AsyncIntegrationTest.java
    TaskSchedulerCancellationTest.java
    OwnedExecutorLifecycleTest.java
  src/test/resources/
    application.properties
~~~

### 10.1 settings.gradle

~~~groovy
rootProject.name = 'async-test-demo'
~~~

### 10.2 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is the Gradle config for the example, without claiming those versions are the latest. The test suite targets Java 17+, Boot 3.5.x. If the machine lacks a Gradle wrapper, generate one or use a compatible installed Gradle.

### 10.3 src/test/resources/application.properties

~~~properties
demo.maintenance.cron=-
logging.level.org.springframework.scheduling=INFO
~~~

## 11. Production: AsyncDemoApplication.java

~~~java
package example.async;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableAsync
@EnableScheduling
public class AsyncDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncDemoApplication.class, args);
    }
}
~~~

`@EnableAsync` enables async proxies; `@EnableScheduling` registers schedules for `@Scheduled` methods. Tests set cron to `'-'` so no background cron runs.

## 12. Production: ExecutorConfig.java

~~~java
package example.async;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration
public class ExecutorConfig {

    @Bean("workExecutor")
    ThreadPoolTaskExecutor workExecutor() {
        ThreadPoolTaskExecutor pool =
                new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("demo-work-");
        pool.setWaitForTasksToCompleteOnShutdown(false);
        pool.setAwaitTerminationSeconds(3);
        pool.setStrictEarlyShutdown(true);
        return pool;
    }

    @Bean("taskScheduler")
    ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("demo-sched-");
        scheduler.setRemoveOnCancelPolicy(true);
        scheduler.setWaitForTasksToCompleteOnShutdown(false);
        scheduler.setAwaitTerminationSeconds(3);
        return scheduler;
    }
}
~~~

Spring initializes and destroys the executor/scheduler beans automatically. Tests do not call `initialize()` manually on these Spring beans. Pool sizes are demo values; production needs appropriate bounded concurrency and rejection/queue policies.

## 13. Production: AsyncWorker.java

~~~java
package example.async;

import java.util.Locale;
import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncWorker {

    @Async("workExecutor")
    public CompletableFuture<String> upper(String input) {
        String value = Thread.currentThread().getName()
                + ":" + input.toUpperCase(Locale.ROOT);
        return CompletableFuture.completedFuture(value);
    }

    @Async("workExecutor")
    public CompletableFuture<String> fail() {
        throw new IllegalStateException("worker failed");
    }
}
~~~

Methods are invoked through the Spring-injected bean so `@Async` advice genuinely executes. `fail()` throws inside the worker; callers receive it via the completion stage.

## 14. Production: ScheduledMaintenance.java

~~~java
package example.async;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ScheduledMaintenance {

    private final AtomicInteger runs = new AtomicInteger();

    @Scheduled(cron = "${demo.maintenance.cron:-}")
    public void runOnce() {
        runs.incrementAndGet();
    }

    public int count() {
        return runs.get();
    }
}
~~~

Spring's property placeholder in the annotation above defaults to `'-'` (cron disabled). The counter only helps tests observe runs; production should extract business logic into an idempotent service if multiple app instances can run the schedule.

## 15. Test support: BlockingJob.java

~~~java
package example.async;

import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

final class BlockingJob implements Callable<String> {

    final CountDownLatch started = new CountDownLatch(1);
    final CountDownLatch release = new CountDownLatch(1);
    final CountDownLatch finished = new CountDownLatch(1);
    final AtomicBoolean interrupted = new AtomicBoolean(false);

    @Override
    public String call() {
        started.countDown();

        try {
            release.await();
            return "released";
        } catch (InterruptedException ex) {
            interrupted.set(true);
            Thread.currentThread().interrupt();
            return "interrupted";
        } finally {
            finished.countDown();
        }
    }
}
~~~

The three latches serve distinct purposes:

- `started` confirms the task actually started before the test cancels.
- `release` lets the test actively end the wait.
- `finished` confirms the task body exited through `finally`.

No sleep is used to guess when the worker starts. `AtomicBoolean interrupted` lets tests prove an interrupt was observed rather than checking only `Future` state.

## 16. AsyncIntegrationTest.java: 7 tests

File `src/test/java/example/async/AsyncIntegrationTest.java`:

~~~java
package example.async;

import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = "demo.maintenance.cron=-")
class AsyncIntegrationTest {

    @Autowired AsyncWorker asyncWorker;
    @Autowired ScheduledMaintenance maintenance;

    @Autowired
    @Qualifier("workExecutor")
    ThreadPoolTaskExecutor executor;

    @Test
    void asyncUsesConfiguredWorker() throws Exception {
        String result = asyncWorker.upper("hello")
                .get(2, TimeUnit.SECONDS);

        assertTrue(result.startsWith("demo-work-"));
        assertTrue(result.endsWith(":HELLO"));
    }

    @Test
    void asyncErrorReachesFuture() throws Exception {
        CompletableFuture<String> future = asyncWorker.fail();

        ExecutionException error = assertThrows(
                ExecutionException.class,
                () -> future.get(2, TimeUnit.SECONDS));

        assertInstanceOf(IllegalStateException.class,
                error.getCause());
        assertEquals("worker failed",
                error.getCause().getMessage());
    }

    @Test
    void timedOutGetDoesNotCancelTask() throws Exception {
        BlockingJob job = new BlockingJob();
        Future<String> future = executor.submit(job);

        try {
            assertTrue(job.started.await(2, TimeUnit.SECONDS));
            assertThrows(TimeoutException.class,
                    () -> future.get(100, TimeUnit.MILLISECONDS));
            assertFalse(future.isDone());
            assertFalse(job.interrupted.get());
        } finally {
            job.release.countDown();
        }

        assertTrue(job.finished.await(2, TimeUnit.SECONDS));
        assertEquals("released", future.get(2, TimeUnit.SECONDS));
    }

    @Test
    void cancelTrueInterruptsResponsiveJob() throws Exception {
        BlockingJob job = new BlockingJob();
        Future<String> future = executor.submit(job);

        try {
            assertTrue(job.started.await(2, TimeUnit.SECONDS));
            assertTrue(future.cancel(true));
            assertTrue(future.isCancelled());
            assertTrue(job.finished.await(2, TimeUnit.SECONDS));
            assertTrue(job.interrupted.get());
            assertThrows(CancellationException.class, future::get);
        } finally {
            job.release.countDown();
            future.cancel(true);
        }
    }

    @Test
    void cancelFalseDoesNotInterruptRunningJob()
            throws Exception {

        BlockingJob job = new BlockingJob();
        Future<String> future = executor.submit(job);

        try {
            assertTrue(job.started.await(2, TimeUnit.SECONDS));
            assertTrue(future.cancel(false));
            assertTrue(future.isCancelled());
            assertFalse(job.interrupted.get());
            assertEquals(1L, job.finished.getCount());
        } finally {
            job.release.countDown();
        }

        assertTrue(job.finished.await(2, TimeUnit.SECONDS));
        assertFalse(job.interrupted.get());
        assertThrows(CancellationException.class, future::get);
    }

    @Test
    void completableFutureCancelDoesNotInterruptWorker()
            throws Exception {

        BlockingJob job = new BlockingJob();
        CompletableFuture<String> visible =
                new CompletableFuture<>();

        Future<?> physical = executor.submit(
                () -> visible.complete(job.call()));

        try {
            assertTrue(job.started.await(2, TimeUnit.SECONDS));
            assertTrue(visible.cancel(true));
            assertTrue(visible.isCancelled());
            assertFalse(job.interrupted.get());
            assertEquals(1L, job.finished.getCount());
        } finally {
            job.release.countDown();
        }

        assertTrue(job.finished.await(2, TimeUnit.SECONDS));
        physical.get(2, TimeUnit.SECONDS);
        assertFalse(job.interrupted.get());
        assertTrue(visible.isCancelled());
    }

    @Test
    void cronDisabledInTestContext() {
        assertEquals(0, maintenance.count());
        maintenance.runOnce();
        assertEquals(1, maintenance.count());
    }
}
~~~

**7 `@Test` methods**. None of the tests shut down the Spring-managed `executor`. Each test releases/cancels the tasks it created.

**Timeout test:** `get(100ms)` throws `TimeoutException` yet the task keeps waiting. After release, the worker finishes and the `Future` returns `released`.

**Cancel true:** after the started signal, `cancel(true)` interrupts the worker awaiting the latch; the test awaits `finished` and checks `interrupted=true`.

**Cancel false:** `Future` is cancelled, yet the job stays waiting on the latch without being interrupted; after release the body finishes normally, while the cancelled `Future` does not return the value.

**CompletableFuture:** cancelling the visible stage does not interrupt the physical worker; the test still must release and await the physical `Future`.

## 17. TaskSchedulerCancellationTest.java: 3 tests

File `src/test/java/example/async/TaskSchedulerCancellationTest.java`:

~~~java
package example.async;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TaskSchedulerCancellationTest {

    private ThreadPoolTaskScheduler scheduler;

    @BeforeEach
    void openOwnedScheduler() {
        scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("test-scheduler-");
        scheduler.setRemoveOnCancelPolicy(true);
        scheduler.initialize();
    }

    @AfterEach
    void closeOwnedScheduler() throws Exception {
        scheduler.shutdown();
        assertTrue(scheduler.getScheduledThreadPoolExecutor()
                .awaitTermination(3, TimeUnit.SECONDS));
    }

    @Test
    void cancelDelayedTaskBeforeStart() {
        AtomicInteger calls = new AtomicInteger();

        ScheduledFuture<?> handle = scheduler.schedule(
                () -> calls.incrementAndGet(),
                Instant.now().plus(Duration.ofDays(1)));

        assertNotNull(handle);
        assertTrue(handle.cancel(false));
        assertTrue(handle.isCancelled());
        assertEquals(0, calls.get());
    }

    @Test
    void interruptRunningPeriodicTask() throws Exception {
        BlockingJob job = new BlockingJob();
        AtomicInteger runs = new AtomicInteger();

        ScheduledFuture<?> handle =
                scheduler.scheduleAtFixedRate(
                    () -> {
                        runs.incrementAndGet();
                        job.call();
                    },
                    Duration.ofMillis(20));

        try {
            assertTrue(job.started.await(2, TimeUnit.SECONDS));
            assertTrue(handle.cancel(true));
            assertTrue(job.finished.await(2, TimeUnit.SECONDS));
            assertTrue(job.interrupted.get());
            assertEquals(1, runs.get());
        } finally {
            job.release.countDown();
            handle.cancel(true);
        }
    }

    @Test
    void cancelHandleDoesNotDestroyScheduler()
            throws Exception {

        ScheduledFuture<?> first = scheduler.schedule(
                () -> {},
                Instant.now().plus(Duration.ofDays(1)));

        assertNotNull(first);
        assertTrue(first.cancel(false));

        CountDownLatch ran = new CountDownLatch(1);
        ScheduledFuture<?> second = scheduler.schedule(
                ran::countDown, Instant.now());

        assertNotNull(second);
        assertTrue(ran.await(2, TimeUnit.SECONDS));
        second.get(2, TimeUnit.SECONDS);
    }
}
~~~

**3 tests**. Each method creates a fresh scheduler. `@AfterEach` shuts it down and asserts `awaitTermination` so no threads leak into other tests. The periodic task blocks during its first run so the test can cancel without sleeping across multiple periods.

`ScheduledFuture.cancel` cancels one registration, **not** the pool; the third test proves the scheduler can continue accepting other tasks.

## 18. OwnedExecutorLifecycleTest.java: 2 tests

File `src/test/java/example/async/OwnedExecutorLifecycleTest.java`:

~~~java
package example.async;

import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OwnedExecutorLifecycleTest {

    private static ThreadPoolTaskExecutor owned(
            boolean graceful) {

        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(2);
        executor.setThreadNamePrefix("owned-test-");
        executor.setWaitForTasksToCompleteOnShutdown(graceful);
        executor.setAwaitTerminationSeconds(3);
        executor.initialize();
        return executor;
    }

    @Test
    void gracefulShutdownDrainsQueue() throws Exception {
        ThreadPoolTaskExecutor executor = owned(true);
        BlockingJob job = new BlockingJob();
        AtomicInteger queuedRuns = new AtomicInteger();

        try {
            Future<String> first = executor.submit(job);
            assertTrue(job.started.await(2, TimeUnit.SECONDS));

            Future<Integer> second =
                    executor.submit(queuedRuns::incrementAndGet);

            job.release.countDown();
            executor.shutdown();

            assertEquals("released",
                    first.get(2, TimeUnit.SECONDS));
            assertEquals(1,
                    second.get(2, TimeUnit.SECONDS));
            assertEquals(1, queuedRuns.get());
            assertTrue(executor.getThreadPoolExecutor()
                    .awaitTermination(3, TimeUnit.SECONDS));
        } finally {
            job.release.countDown();
            executor.shutdown();
        }
    }

    @Test
    void interruptingShutdownEndsResponsiveJob()
            throws Exception {

        ThreadPoolTaskExecutor executor = owned(false);
        BlockingJob job = new BlockingJob();

        try {
            executor.submit(job);
            assertTrue(job.started.await(2, TimeUnit.SECONDS));
            executor.shutdown();

            assertTrue(job.finished.await(2, TimeUnit.SECONDS));
            assertTrue(job.interrupted.get());
            assertTrue(executor.getThreadPoolExecutor()
                    .awaitTermination(3, TimeUnit.SECONDS));
        } finally {
            job.release.countDown();
            executor.shutdown();
        }
    }
}
~~~

**2 tests**. Graceful shutdown with `waitForTasksToCompleteOnShutdown=true` allows running and queued tasks to finish. Interrupting shutdown with `false` requests interrupting the job waiting on the latch; the test checks both interruption and underlying pool termination.

This pool is **created per test**, not a Spring-managed shared bean, so `shutdown()` follows proper ownership.

## 19. Summary of 12 JUnit Jupiter tests

| Test class | Method count | Scenario |
| --- | ---: | --- |
| `AsyncIntegrationTest` | 7 | `@Async` proxy, Future timeout, cancel true/false, `CompletableFuture`, cron disable |
| `TaskSchedulerCancellationTest` | 3 | Cancelling delayed/periodic schedules, scheduler shutdown |
| `OwnedExecutorLifecycleTest` | 2 | Graceful vs interrupting executor shutdown |
| **Total** | **12** | No sleep, no external resources |

In a project with a Gradle wrapper:

~~~bash
./gradlew test --tests example.async.AsyncIntegrationTest --tests example.async.TaskSchedulerCancellationTest --tests example.async.OwnedExecutorLifecycleTest
~~~

Windows:

~~~powershell
.\gradlew.bat test --tests example.async.AsyncIntegrationTest --tests example.async.TaskSchedulerCancellationTest --tests example.async.OwnedExecutorLifecycleTest
~~~

**Expected outcome by design:** 12 tests PASS on Java 17+/Spring Boot 3.5.x with the code/dependencies/file paths above. This is **not** stdout captured from an actual Gradle build. The 2–3 second waits in tests are upper bounds on failure, not a promise about suite duration.

### If tests hang

1. Inspect `Thread.dump` or `jstack` to see what the worker is waiting on.
2. Check that all latches are released in `finally`.
3. Check whether tasks catch `InterruptedException` and keep looping.
4. Check whether an earlier test class shut down a shared executor bean.
5. Check whether tasks are stuck in the queue due to pool saturation.
6. Check that cron schedules are not unintentionally enabled in the test context.
7. Check that `@Async` runs through the Spring proxy, not self-invocation.
8. Check that HTTP/DB drivers have real timeouts, not just `Future` timeouts.
9. Check that test-created executors/schedulers were shut down and awaited termination.
10. Check thread name prefixes to identify exact owners instead of JVM-wide `Thread.activeCount`.

## 20. Thread pool saturation and rejection

Typical `ThreadPoolTaskExecutor`:

~~~text
corePoolSize=2
maxPoolSize=4
queueCapacity=3

tasks 1-2       -> 2 worker threads
tasks 3-5       -> queued
tasks 6-7       -> can scale up to 4 worker threads
next task       -> rejected if both threads and queue are full
~~~

This is a conceptual diagram when tasks block and the queue has not drained. With an unbounded queue, the pool may **never** scale up to `maxPoolSize` because the queue always accepts tasks first.

To test rejection, submit a task waiting on a latch so workers stay busy, fill the queue, and assert `TaskRejectedException`/configured handler. **Never** leave the first task waiting indefinitely after an assertion failure; clean up in `finally`.

`CallerRunsPolicy` can run tasks on the **caller thread** under overload, so assumptions that "this runs async" must check the rejection handler.

## 21. Transactions, SecurityContext, and MDC in async threads

### 21.1 Spring TestContext transactions do not follow @Async

Spring TestContext normally binds transactions to the **JUnit test thread**. `@Async`/`@Scheduled` run on other threads, so the test's JDBC transaction does not carry over. If the worker opens its own transaction or uses auto-commit, data can persist **after the test rolls back**.

Use committed cleanup or an isolated test database instead of relying on `@Rollback` to clean up background writes.

### 21.2 SecurityContext does not follow workers automatically

`SecurityContextHolder` is thread-bound by default. New workers do not automatically get JUnit's security identity, nor do MDC/tenant `ThreadLocal`s propagate automatically. When business needs it, use `DelegatingSecurityContextAsyncTaskExecutor`, `TaskDecorator`, or proper context propagation with **`finally` clearing** to avoid leaking identity across pooled tasks.

### 21.3 EntityManager is not thread-safe

Do not share the same persistence context/`EntityManager`/JDBC Connection across worker threads. Services on worker threads should open their own transactions through Spring proxies when needed. Never share a mutable DB session to "keep the test transaction" across threads.

## 22. Cron, fixed delay, and cluster consistency

- `fixedRate`: test schedule semantics separately if an exact cadence is required.
- `fixedDelay`: wait duration after completion; suited to preventing overlap on a single scheduled registration.
- `cron`: requires timezone when schedules tie to local time/DST.
- Multiple `@Scheduled` annotations on one method can register multiple triggers.
- Running Spring Boot across multiple replicas typically gives **each instance** its own scheduler.
- Jobs with side effects need idempotency, distributed locking, or a persistent scheduler if cluster-wide once semantics are required.

Never run a JUnit test with one `ApplicationContext` and conclude "the job runs only once across the distributed system".

## 23. Cleanup matrix

| Resource | Owner | Cleanup |
| --- | --- | --- |
| `Future` from test-submitted task | Test | cancel/release, await finished latch |
| `CompletableFuture` completion stage | Caller | cancel stage; handle physical task separately |
| `ExecutorService` created in test | Test | `shutdown`/`shutdownNow` + `awaitTermination` |
| Spring-bean `ThreadPoolTaskExecutor` | `ApplicationContext` | test cleans up its own tasks; Spring closes on context close |
| Test-owned `ThreadPoolTaskScheduler` | Test | cancel `ScheduledFuture`, shutdown, await |
| `@Scheduled` registration | Spring context | cron disabled in ordinary tests, close context when owned |
| DB writes from workers | Database/app transaction | Dedicated test DB, clean up committed rows |
| HTTP call | HTTP client | per-resource timeout, cancel/close response |
| Message consumer | Container/broker | stop listener, unsubscribe/offset cleanup |
| Temp files | Test | `@TempDir`/`try-finally` |
| Reactive subscription | Subscriber | dispose/cancel and verify terminal state |
| Quartz/distributed job | Scheduler persistence | unschedule and clean up locks/fixtures |

**Do not use `@DirtiesContext` as the default choice to clean up executors**: context rebuilds are slow and do not delete committed database side effects. Use it only when a test genuinely needs to destroy and restart the Spring context and lifecycle.

## 24. Common mistakes

**1. `TimeoutException` means the task was cancelled.**  
Wrong: `get(timeout)` does not auto-cancel.

**2. `Future.isDone()` means the worker exited.**  
Wrong: a cancelled future is also done.

**3. `CompletableFuture.cancel(true)` interrupts the worker.**  
Wrong in Java 17's implementation; you need the physical task handle.

**4. `Future.cancel(false)` stops a running task.**  
It requests no interrupt; the task can continue.

**5. `Future.cancel(true)` guarantees interrupting any I/O.**  
Interruption is best effort; resource-specific cancellation is required.

**6. Catching `InterruptedException`, swallowing it, and continuing the loop.**  
Prevents the pool from shutting down cleanly; exit or propagate appropriately.

**7. Not releasing latches in `finally`.**  
Assertion failures leave workers stuck forever.

**8. Using `Thread.sleep` to wait for `@Async`.**  
Flaky on CI; use `CountDownLatch` and bounded `get`.

**9. `@Async void` exceptions still let tests PASS.**  
Use a handler or a `Future`-based contract to observe errors.

**10. `@Async` self-invocation bypasses the proxy.**  
Extract a bean or call through a Spring-managed proxy.

**11. Test shuts down a shared `@Autowired` executor.**  
Corrupts the cached context; later tests fail with rejections.

**12. Scheduler not cancelled after test.**  
Periodic job keeps running, causing data races/leaks.

**13. `@Scheduled` runs on `SpringBootTest` startup.**  
Disable cron or isolate scheduling configuration.

**14. Testing cron by sleeping until the scheduled wall-clock time.**  
Slow/flaky; use `CronExpression`/`Clock` or a fake scheduler.

**15. `waitForTasksToCompleteOnShutdown=true` with a hung task.**  
Shutdown can wait too long; add deadlines and interrupt responsiveness.

**16. Ignoring `awaitTermination` returning `false`.**  
Resource leaks go unreported; the test should FAIL.

**17. `assertTimeoutPreemptively` inside an `@Transactional` test.**  
The thread boundary can stop DB writes from rolling back with the test.

**18. Relying on `EntityManager`/`SecurityContext` `ThreadLocal` across an executor without propagation.**  
Can run with the wrong thread context or leak identities.

**19. HTTP `Future` times out yet the request keeps running.**  
Configure real HTTP client transport timeouts/cancellation.

**20. Unbounded queue prevents `maxPoolSize` from growing.**  
Configure bounded queues as needed and test rejection.

**21. Asserting `activeCount==0` immediately after `Future` completion.**  
Pool snapshots are not synchronization barriers; use latches and `awaitTermination`.

**22. Treating a multi-instance scheduler as cluster-wide once.**  
Requires distributed coordination/idempotency.

## 25. Checklist before finalizing a test suite

1. Clearly treat caller timeout, worker cancellation, and pool cleanup as three distinct concerns.
2. Give every `Future.get`/`await` in tests a bounded timeout.
3. Add `finally` blocks to release resources even when assertions fail.
4. Provide a worker-finished signal, not just `isDone`/`isCancelled`.
5. Make tasks cooperate with interrupts and clean up connections/files/locks.
6. Verify `CompletableFuture` cancellation against the actual implementation.
7. Invoke `@Async` through a bean/proxy with the right executor qualifier.
8. Avoid `@Async void` without an error observer.
9. Prevent `@Scheduled` from running randomly in ordinary `SpringBootTest`s.
10. Keep business logic tests separate from trigger registration tests.
11. Always shut down test-owned pools/schedulers and await termination.
12. Never shut down Spring-managed executors in cached test contexts.
13. Configure dedicated HTTP/DB timeouts alongside overall deadlines.
14. Clean up committed state for async/scheduled DB writes.
15. Do not rely on `ThreadLocal` security/transaction propagation automatically onto workers.
16. Add idempotency/distributed locks if scheduled jobs run on multiple instances.
17. Test queue saturation/rejection when capacity limits are critical requirements.
18. Re-run the suite and inspect thread dumps when leaks are suspected.

### Final checklist

- [ ] Do not confuse timeouts with cancellation.
- [ ] `Future.cancel(true)` is only an interrupt request.
- [ ] `CompletableFuture.cancel(true)` does not interrupt by default.
- [ ] Tests use latches, not arbitrary sleep.
- [ ] Proof exists that the worker body actually finished.
- [ ] Test-created tasks have `finally` cleanup.
- [ ] Scheduler registrations are cancelled.
- [ ] Owned executors run `shutdown` + `awaitTermination`.
- [ ] Spring-managed executors are not closed prematurely.
- [ ] `@Scheduled` is disabled/isolated when not testing triggers.
- [ ] `@Async` exceptions are observed.
- [ ] Thread-bound transaction/security contexts are handled accurately.

## 26. Conclusion

**Timeouts bound waiting; cancellation requests stopping; cleanup proves tasks and resources have terminated.** In Spring Boot tests, these three must be designed and verified separately.

- `@Async` operates through Spring proxies and executors; use `Future`/`CompletableFuture` with accurate semantics and always wait with bounds.
- `@Scheduled` shares the `ApplicationContext` lifecycle; never let crons run randomly between tests.
- `Future.cancel(true)` can interrupt workers; `CompletableFuture.cancel(true)` does not automatically interrupt physical computation in Java 17.
- Test-owned `ThreadPoolTaskExecutor`/`ThreadPoolTaskScheduler` must be shut down and awaited, while Spring-managed beans belong to the container.
- `CountDownLatch`, `finally`, bounded waits, and end-of-worker latches are far more reliable than `Thread.sleep`.

### Official references

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Async`, `@Scheduled`, executor/scheduler abstractions, and lifecycle.
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): executor auto-config, queue/thread-pool, and scheduling.
- [Spring Boot 3.5 — Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.task.execution`/`scheduling` shutdown settings.
- [Spring Framework 6.2 — ThreadPoolTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): lifecycle, submit, and metrics.
- [Spring Framework 6.2 — ThreadPoolTaskScheduler API](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html): schedule, `ScheduledFuture`, and shutdown.
- [Java SE 17 — Future API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): timed get, cancel, `isDone`/`isCancelled`.
- [Java SE 17 — CompletableFuture API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): cancel and completion/timeout behavior.
- [Java SE 17 — ExecutorService API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown, `shutdownNow`, and `awaitTermination`.
- [Spring TestContext — Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): preemptive timeout/thread-bound transaction warning.