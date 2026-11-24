# Using Timeouts and Completion Signals Instead of Fixed Sleeps in Async Testing

## 1. Problem: a test passes locally yet fails randomly in CI

In Java and Spring Boot, many operations **do not finish immediately on the calling thread**: **`@Async`** methods, tasks in an **`ExecutorService`**, **`CompletableFuture`** callbacks, **`@Scheduled`** tasks, asynchronous MVC requests, event listeners, and **`SmartLifecycle.stop(Runnable)`** can all complete at a later time.

A seemingly simple testing approach is:

~~~java
service.startAsyncJob();
Thread.sleep(1000);
assertEquals("DONE", repository.findStatus());
~~~

This is an **illustrative anti-pattern snippet**, not a standalone program; the objects and methods must be declared in a project. This test has at least three flaws:

1. If the job finishes in 20 ms, the test still wastes nearly 980 ms waiting pointlessly.
2. If CI is slow, the JVM is in GC, the executor is overloaded, or remote I/O takes over a second, the test fails even when logic is correct.
3. If the job never runs, the test only reports a wrong final value without revealing whether the task **started**, was **waiting on a condition**, **errored out**, or was never submitted.

**Principle:** never guess when work finishes using a fixed millisecond count. Wait on **a meaningful signal or condition**, while ensuring **every wait in a test has a deadline** so it never hangs forever.

~~~text
Fragile approach:
@Test thread -> submit work -> sleep(1000) -> assert
                               |
                          guessing time

Controlled approach:
@Test thread -> submit work
                 |
                 +-- worker signals STARTED
                 +-- test awaits STARTED (timeout)
                 +-- test checks intermediate state
                 +-- test fires RELEASE
                 +-- worker signals COMPLETED / Future returns result
                 +-- test awaits COMPLETED (timeout)
                 +-- assert results and cleanup
~~~

This article follows **Java 17+, Spring Boot 3.3.13, Spring Framework 6.1, and JUnit Jupiter 5**. The goal is not replacing every wait with one tool, but picking the right tool for the **completion contract** under test, including startup, shutdown, and cancellation scenarios.

## 2. Distinguishing four milestones in an asynchronous test

A task does not merely have two states ("not done" and "done"). At minimum, distinguish:

| Milestone | Meaning | Useful signal |
| --- | --- | --- |
| **SUBMITTED** | Task was placed in executor/queue | Return of `submit` or matching API |
| **STARTED** | Task code actually entered business section | `CountDownLatch`, observer, or controlled callback |
| **COMPLETED** | Task finished, succeeded or failed | `Future`/`CompletionStage`, `CountDownLatch` in `finally` |
| **CLEANED_UP** | Resources closed/destroyed, no longer serving | `@PreDestroy`, `SmartLifecycle` callback, close state |

**SUBMITTED does not equal STARTED** if the executor has a queue. **STARTED does not equal COMPLETED** if the task awaits I/O or a latch. **COMPLETED does not equal CLEANED_UP** if the executor/context remains alive.

For example, a test proving **`ApplicationContext` waits for a component to finish stopping** cannot wait solely on a "stop requested" signal; it also needs the **`callback.run` ran** signal and the **`context.close()` Future** actually completing.

### 2.1. Why time-based tests always have races

~~~text
Healthy CI:
0 ms: submit
5 ms: task done
1000 ms: test assert -> PASS

Overloaded CI:
0 ms: submit
1000 ms: test assert -> FAIL
1400 ms: task done

Increase sleep to 3000 ms?
- Slower on every test run
- No guarantee if CI is even slower
- Masks actual event ordering
~~~

The bug is not picking the wrong 1000 ms — it is **the test using elapsed time instead of proof that the task reached the milestone under test**.

### 2.2. Can time be used in tests at all?

Yes. A **timeout** is a bounded failure condition, not a **fixed sleep before an assertion**. The difference:

- **`Thread.sleep(1000)`:** always waits roughly one second, ignoring whether the event already occurred.
- **`latch.await(1, SECONDS)`:** returns immediately when count reaches 0, or `false` if expired.
- **`future.get(1, SECONDS)`:** returns immediately when the task ends, or throws `TimeoutException` if expired.
- **`condition-await atMost(1s)`:** checks until the condition holds, within a bound.

Timeout values must reflect a **reasonable test budget**, never a guarantee that hardware/schedulers finish in an exact number of milliseconds.

## 3. Common Java tools: choosing by contract

| Tool | When to use | Outcome on timeout |
| --- | --- | --- |
| **`CountDownLatch.await(timeout, unit)`** | Waiting for one or more explicitly signaled events | Returns **`false`** |
| **`Future.get(timeout, unit)`** | Waiting for task completion and retrieving result/error | Throws **`TimeoutException`** |
| **`CompletableFuture.get(timeout, unit)`** | Waiting for a completion stage with result | Throws **`TimeoutException`** |
| **`CompletableFuture.join()`** | Retrieving result when guaranteed complete | Accepts no timeout directly; can wait forever |
| **`Semaphore.tryAcquire(timeout, unit)`** | Waiting for permit/handoff | Returns `false` |
| **`BlockingQueue.poll(timeout, unit)`** | Waiting for message/event delivered via queue | Returns `null` |
| **`Condition.await(timeout, unit)`** | Waiting for state predicate with lock | Returns deadline status |
| **`Thread.join(millis)`** | Waiting for a self-created thread to exit | Returns on timeout or thread death; must check `isAlive` |
| **`Awaitility await().atMost(...)`** | Waiting for an eventual assertion | Assertion timeout from library |
| **`JUnit @Timeout`** | Bounding total test duration | Test marked failed when deadline exceeded |

No tool automatically turns an async API into one with transactions, retries, or durability. They only help **tests observe completion under explicit conditions**.

### 3.1. CountDownLatch: a one-shot signal

~~~java
CountDownLatch done = new CountDownLatch(1);
worker.runAsync(done::countDown);

assertTrue(done.await(2, TimeUnit.SECONDS));
~~~

This is a snippet assuming `worker` accepts a callback. With **`CountDownLatch(1)`**, `countDown()` drops the counter to 0 and unblocks awaiting threads. **`await(timeout)`** returns immediately if the signal already fired before the test started waiting, avoiding missed one-moment notifications.

A latch **does not reset** after reaching 0. For multi-round cycles or reusable gates, use **`Phaser`**, **`CyclicBarrier`**, or construct a new latch per test/task.

### 3.2. Future: completion paired with result and exception

~~~java
Future<String> result = executor.submit(() -> "ready");
assertEquals("ready", result.get(2, TimeUnit.SECONDS));
~~~

If the task throws an exception, **`Future.get(...)`** throws **`ExecutionException`**, where **`getCause()`** is normally the task's error. On expiration, it throws **`TimeoutException`**, yet **the task is not automatically cancelled** merely because the caller timed out.

### 3.3. CompletableFuture: completion with success or error

~~~java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(() -> "ready");

assertEquals("ready", future.get(2, TimeUnit.SECONDS));
~~~

In this example, `get(timeout)` prevents the test from hanging forever. **`join()`** has no Duration/timeout overload in Java 17, so use it only when completion is already proved or an external deadline is enforced properly.

**`CompletableFuture.orTimeout(...)`** and **`completeOnTimeout(...)`** alter the completion state/value of the configured stage itself; they do not mean underlying I/O or computation was cancelled. In tests, it is usually clearer to use **`get(timeout)`** without altering the object under test.

## 4. Standalone Java 17 demo: STARTED → RELEASE → COMPLETED

Create file **`SignalInsteadOfSleep.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class SignalInsteadOfSleep {

    public static void main(String[] args) throws Exception {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        try {
            Future<String> future = executor.submit(() -> {
                started.countDown();

                if (!release.await(5, TimeUnit.SECONDS)) {
                    throw new TimeoutException(
                            "Worker never received release signal");
                }

                return "READY";
            });

            if (!started.await(2, TimeUnit.SECONDS)) {
                throw new AssertionError("Worker did not start");
            }

            if (future.isDone()) {
                throw new AssertionError(
                        "Worker finished before release");
            }

            release.countDown();

            String value = future.get(2, TimeUnit.SECONDS);
            System.out.println(value);
        } finally {
            release.countDown();
            executor.shutdownNow();
            if (!executor.awaitTermination(
                    2, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Executor did not terminate");
            }
        }
    }
}
~~~

Run with JDK 17+:

~~~bash
javac SignalInsteadOfSleep.java
java SignalInsteadOfSleep
~~~

**Program stdout on successful completion:**

~~~text
READY
~~~

This example includes full imports, class, and `main`, with no Spring dependency. Three key synchronization steps:

1. **`started.await(2s)`** ensures the worker entered the callable, rather than guessing with sleep.
2. **`future.isDone()`** right after started is false because the worker awaits **`release`**, unless the worker's internal deadline expired; if that happens, the test fails clearly.
3. **`release.countDown()`** opens the gate; **`future.get(2s)`** awaits actual completion and retrieves the result.

The **`finally`** block fires release once more so no blocked worker is left behind if an earlier assertion failed; **`CountDownLatch.countDown()`** is idempotent after reaching 0. Afterward the executor is shut down and awaited within bounds.

### 4.1. Why does the worker still have an internal timeout?

The **test** wait and the **worker** wait are two distinct deadlines. If the test fails midway or the test thread is interrupted, the worker still must not wait indefinitely on the latch. The internal five-second deadline is a **safety guardrail** of the fixture, not a sleep.

### 4.2. Why not use a plain boolean?

A variable:

~~~java
boolean completed = false;
~~~

written by a worker and read by a test on another thread can suffer visibility issues. **`CountDownLatch`**, **`Future`**, **`AtomicBoolean`**, **`volatile`**, and synchronization primitives provide proper memory visibility guarantees.

Merely switching to:

~~~java
volatile boolean completed;
~~~

and polling in a `while` loop does not solve CPU spinning or timeouts. For one-shot events, latches/Futures express the contract much more cleanly.

### 4.3. happens-before matters more than timestamps

When a worker calls **`CountDownLatch.countDown()`**, actions before `countDown` have a **happens-before** relationship with actions after another thread successfully **`await`**s that latch.

Thus:

~~~java
result = "DONE";
done.countDown();
~~~

and after **`done.await(...)`** succeeds, the test reads `result` under proper synchronization. **`Thread.sleep(...)`** does not establish such a happens-before relationship; merely waiting over time never guarantees visibility.

## 5. Using @Async in Spring Boot: do not test with sleep

In Spring Boot, a method:

~~~java
@Async
public CompletableFuture<String> generateReport(String id) {
    return CompletableFuture.completedFuture("report:" + id);
}
~~~

is a snippet requiring a Spring bean, **`@EnableAsync`**, and **invocation through a Spring proxy**. When called from another bean, the invocation runs on an executor thread and the caller receives a `CompletableFuture` to await completion.

**Watch out for self-invocation:** if a method in the same object calls **`this.generateReport(...)`**, proxy-based `@Async` does not intercept internal calls by default, so testing with `Thread.sleep` can mask the bug that the method isn't actually async. Tests must call through a **Spring-injected bean/proxy**.

If a method returns **`void`**, callers have no Future to observe exceptions/completion directly. Whenever possible, return a **`CompletableFuture`** or design an explicit event/callback for testing.

### 5.1. Stable testing model

Tests should not wait "around one second for `@Async` to finish". Instead:

- Fake dependency has an **entered latch** signaling the async method truly entered.
- Fake dependency has a **release latch** holding work at an intentional point.
- Test awaits `entered` with a timeout.
- Test confirms the Future is not done while the dependency is unreleased.
- Test fires `release`.
- Test retrieves the result with **`future.get(timeout)`**.
- Test always releases in `finally` to prevent leaking worker threads.

This is an ordering test, not a benchmark.

## 6. Complete Spring Boot 3.3 + JUnit 5 example

The following project uses Spring Boot without a web server, focusing on testing **`@Async`**, with a fake gateway controlled by two latches. All classes and files compile in a Java 17+ Maven project.

### 6.1. Structure

~~~text
async-lifecycle-test-demo/
  pom.xml
  src/main/java/com/example/lifecycle/AsyncLifecycleDemo.java
  src/test/java/com/example/lifecycle/AsyncReportTest.java
  src/test/java/com/example/lifecycle/SmartLifecycleStopTest.java
  src/test/java/com/example/lifecycle/ContextCloseSignalTest.java
~~~

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>async-lifecycle-test-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-test` supplies **JUnit Jupiter** and the integrations needed for **`@SpringBootTest`**. The example intentionally **omits `spring-boot-starter-web`**, because an HTTP server is unnecessary when testing an async service and context lifecycle.

### 6.3. AsyncLifecycleDemo.java

Create **`src/main/java/com/example/lifecycle/AsyncLifecycleDemo.java`**:

~~~java
package com.example.lifecycle;

import java.util.concurrent.CompletableFuture;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;

@SpringBootApplication
@EnableAsync
public class AsyncLifecycleDemo {

    public static void main(String[] args) {
        SpringApplication.run(AsyncLifecycleDemo.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class AsyncConfiguration {

    @Bean("reportExecutor")
    ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("report-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(3);
        return executor;
    }
}

interface ReportGateway {
    String fetch(String id);
}

@Component
class DefaultReportGateway implements ReportGateway {

    @Override
    public String fetch(String id) {
        return "report:" + id;
    }
}

@Service
class ReportService {

    private final ReportGateway gateway;

    ReportService(ReportGateway gateway) {
        this.gateway = gateway;
    }

    @Async("reportExecutor")
    public CompletableFuture<String> generate(String id) {
        String value = gateway.fetch(id);
        return CompletableFuture.completedFuture(value);
    }
}
~~~

**Explanation:**

- **`@EnableAsync`** enables `@Async` processing via Spring infrastructure.
- **`@Async("reportExecutor")`** selects the declared `ThreadPoolTaskExecutor` bean by name.
- **`ReportService`** must be called via a Spring bean (proxy), never directly on a `new`-instantiated instance.
- **`ReportGateway`** is a dependency replaceable with a fake in tests.
- Returning **`CompletableFuture`** lets callers inspect completion and exceptions.
- `ThreadPoolTaskExecutor` is Spring-managed; shutdown config awaits running tasks within a bounded period. In production, timeout/queue policies must fit workload; the demo uses small values for observability.
- Since there is only one public top-level class, the filename **`AsyncLifecycleDemo.java`** matches. Remaining classes have package visibility in the same package.

**Detail on `@Async` returning `CompletableFuture`:** the implementation may return an already-completed `CompletableFuture` inside the executor thread; the async proxy returns a stage representing task execution to the caller. **Do not conclude the caller's Future is already complete merely because the method body uses `completedFuture`**; the method body must actually run first.

### 6.4. AsyncReportTest.java: controlling entry and completion milestones

Create **`src/test/java/com/example/lifecycle/AsyncReportTest.java`**:

~~~java
package com.example.lifecycle;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = {
                AsyncLifecycleDemo.class,
                AsyncReportTest.GatewayTestConfiguration.class
        },
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class AsyncReportTest {

    @Autowired
    private ReportService reportService;

    @Autowired
    private ControlledGateway gateway;

    @Test
    @Timeout(
            value = 10,
            unit = TimeUnit.SECONDS,
            threadMode = Timeout.ThreadMode.SAME_THREAD)
    void waitsForActualCompletionInsteadOfSleeping()
            throws Exception {

        CompletableFuture<String> future =
                reportService.generate("42");

        try {
            assertTrue(
                    gateway.entered.await(2, TimeUnit.SECONDS),
                    "Async service never reached gateway");

            assertFalse(
                    future.isDone(),
                    "Future must wait while gateway is blocked");

            gateway.release.countDown();

            assertEquals(
                    "report:42",
                    future.get(3, TimeUnit.SECONDS));
        } finally {
            gateway.release.countDown();
        }
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class GatewayTestConfiguration {

        @Bean
        @Primary
        ControlledGateway controlledGateway() {
            return new ControlledGateway();
        }
    }

    static final class ControlledGateway
            implements ReportGateway {

        final CountDownLatch entered = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);

        @Override
        public String fetch(String id) {
            entered.countDown();

            try {
                if (!release.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Test gateway was not released");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Gateway interrupted", ex);
            }

            return "report:" + id;
        }
    }
}
~~~

This is a real **`@SpringBootTest`**:

1. Spring initializes the application context.
2. **`@Primary ControlledGateway`** takes precedence over `DefaultReportGateway`.
3. The test invokes **`ReportService` through the Spring proxy**, triggering the executor.
4. The fake signals **`entered`** when the async worker enters `gateway.fetch`.
5. The worker awaits **`release`**, so the Future is not yet done.
6. The test asserts intermediate state **without sleeping**.
7. The test fires `release` and retrieves the result via **`Future.get(3s)`**.
8. `finally` always opens the gate to reduce hanging risks if an assertion fails.

**The `entered` signal fires before `await`**, so once the test observes `entered` cleanly before firing `release`, **`future.isDone()`** cannot become true via normal completion. If the worker timed out internally, that too is an error and requires appropriate deadlines in the fixture.

### 6.5. Running the test

~~~bash
java -version
mvn test
~~~

When assertions pass, Maven Surefire reports **`BUILD SUCCESS`**. There is no fixed stdout from application code in the test because the test suite prints nothing to console; do not depend on thread names or Spring log ordering.

### 6.6. Why is a fake gateway better than sleeping 1 second?

The fake controls **the exact point under observation** inside the dependency. This enables:

- Proving `@Async` actually began executing.
- Proving the caller can observe the incomplete state.
- Completing the task via explicit release.
- Independence from scheduling speed.
- Clear failure messages if a milestone is missed within the timeout.
- Avoiding real remote API calls or touching real databases merely to test timing.

For integration tests, you can swap the fake for a local HTTP stub or Testcontainers, while still awaiting a health/readiness signal instead of a fixed sleep after container start.

## 7. Testing asynchronous shutdown of SmartLifecycle

**SmartLifecycle** in Spring Framework supports components starting/stopping with the lifecycle. The special method:

~~~java
void stop(Runnable callback);
~~~

lets a component signal stopping **asynchronously**. Per Spring Framework 6.1 docs, the implementation **must call `callback.run()` after stopping genuinely completes**; if forgotten, `LifecycleProcessor` may wait until the shutdown phase timeout expires.

This is an ideal test problem for three signals:

- **`stopRequested`:** the framework invoked `stop(Runnable)`.
- **`allowStop`:** the test permits stop work to complete.
- **`stopCallbackFinished`:** the callback has executed.

The test must also verify **`ApplicationContext.close()` has not completed before the stop callback fires**, and after release the close `Future` finishes.

### 7.1. SmartLifecycleStopTest.java

Create **`src/test/java/com/example/lifecycle/SmartLifecycleStopTest.java`**:

~~~java
package com.example.lifecycle;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SmartLifecycleStopTest {

    @Test
    @Timeout(
            value = 12,
            unit = TimeUnit.SECONDS,
            threadMode = Timeout.ThreadMode.SAME_THREAD)
    void contextCloseWaitsForStopCallback() throws Exception {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        ExecutorService closeCaller =
                Executors.newSingleThreadExecutor();

        ControlledStop component = null;

        try {
            context.registerBean(
                    ControlledStop.class,
                    ControlledStop::new);
            context.refresh();

            component = context.getBean(ControlledStop.class);
            assertTrue(component.isRunning());

            Future<?> closeFuture =
                    closeCaller.submit(context::close);

            assertTrue(
                    component.stopRequested.await(
                            2, TimeUnit.SECONDS),
                    "stop(Runnable) was not called");

            assertFalse(
                    closeFuture.isDone(),
                    "Context closed before stop was released");

            component.allowStop.countDown();

            closeFuture.get(4, TimeUnit.SECONDS);

            assertTrue(
                    component.stopCallbackFinished.await(
                            1, TimeUnit.SECONDS));

            assertFalse(component.isRunning());
            assertFalse(component.waitTimedOut.get());
        } finally {
            if (component != null) {
                component.allowStop.countDown();
            }
            context.close();
            closeCaller.shutdownNow();
            closeCaller.awaitTermination(2, TimeUnit.SECONDS);
        }
    }

    static final class ControlledStop
            implements SmartLifecycle {

        final CountDownLatch stopRequested =
                new CountDownLatch(1);
        final CountDownLatch allowStop =
                new CountDownLatch(1);
        final CountDownLatch stopCallbackFinished =
                new CountDownLatch(1);
        final AtomicBoolean waitTimedOut =
                new AtomicBoolean(false);

        private volatile boolean running;

        @Override
        public void start() {
            running = true;
        }

        @Override
        public void stop(Runnable callback) {
            stopRequested.countDown();

            Thread finisher = new Thread(() -> {
                try {
                    if (!allowStop.await(
                            6, TimeUnit.SECONDS)) {
                        waitTimedOut.set(true);
                    }
                } catch (InterruptedException ex) {
                    waitTimedOut.set(true);
                    Thread.currentThread().interrupt();
                } finally {
                    running = false;
                    try {
                        callback.run();
                    } finally {
                        stopCallbackFinished.countDown();
                    }
                }
            }, "controlled-stop-fixture");

            finisher.setDaemon(true);
            finisher.start();
        }

        @Override
        public void stop() {
            running = false;
            allowStop.countDown();
        }

        @Override
        public boolean isRunning() {
            return running;
        }

        @Override
        public int getPhase() {
            return 0;
        }
    }
}
~~~

**Test logic explanation:**

- **`AnnotationConfigApplicationContext`** is a real Spring context requiring no Spring Boot embedded server.
- **`registerBean(ControlledStop.class, ControlledStop::new)`** creates a context-managed bean.
- **`context.refresh()`** auto-starts `SmartLifecycle` beans (default **`isAutoStartup()=true`**).
- **`closeCaller.submit(context::close)`** closes the context on another thread so the test can keep controlling the gate.
- **`stopRequested.await(2s)`** confirms the framework invoked the callback-accepting `stop` method.
- While **`allowStop`** is unreleased, the stop fixture is waiting; hence **`closeFuture.isDone()`** must be false.
- After release, the fixture calls **`callback.run()`** in `finally`, signals **`stopCallbackFinished`**, and sets `running=false`.
- **`closeFuture.get(4s)`** verifies `context.close()` completed, not merely that `stopRequested` fired.
- `finally` releases the gate and executor if a test assertion fails. The fixture has an internal timeout so it never leaves workers alive indefinitely.

**Production note:** the thread inside `ControlledStop` is a **test fixture** intentionally awaiting a test-controlled gate. A production `SmartLifecycle` must actually stop real resources, invoke the callback once resources have stopped, and never wait on test gates; implement an explicit state machine, timeouts, and idempotency.

### 7.2. Why is calling callback.run() so important?

Spring Framework's `LifecycleProcessor` relies on the callback to know when the phase can proceed. If the callback is forgotten:

- Context shutdown can stall until the phase timeout.
- Tests can fail on timeout even though resources actually stopped.
- During DevTools restarts, restarts can become slow or hang.
- When the process receives `SIGTERM`, the termination grace budget can be exhausted.

In the test Java code, **`callback.run()` sits in `finally`** so it is not skipped after an `InterruptedException`. In production, never mark stop successful while the component is still running; design error states with clear semantics.

### 7.3. Never treat stopRequested as proof shutdown finished

A test:

~~~java
assertTrue(stopRequested.await(2, TimeUnit.SECONDS));
~~~

only indicates **stop has started**. It does not prove:

- Worker threads exited.
- Resources closed.
- The callback executed.
- `ApplicationContext.close()` returned.

To assert completion, use the close command's Future or a **`stopCompleted`** signal emitted at the exact completion point.

## 8. Checking ContextClosedEvent and @PreDestroy with signals

Beyond `SmartLifecycle`, latches can verify two milestones:

1. **`ContextClosedEvent`** is emitted when the context closes.
2. **`@PreDestroy`** is invoked during destruction of managed beans.

### 8.1. ContextCloseSignalTest.java

Create **`src/test/java/com/example/lifecycle/ContextCloseSignalTest.java`**:

~~~java
package com.example.lifecycle;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.annotation.PreDestroy;
import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.ContextClosedEvent;

import static org.junit.jupiter.api.Assertions.assertTrue;

class ContextCloseSignalTest {

    @Test
    void closeEmitsEventAndDestroysBean() throws Exception {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        try {
            context.registerBean(
                    CloseSignals.class,
                    CloseSignals::new);
            context.refresh();

            CloseSignals signals =
                    context.getBean(CloseSignals.class);

            context.close();

            assertTrue(signals.closing.await(
                    1, TimeUnit.SECONDS));
            assertTrue(signals.destroyed.await(
                    1, TimeUnit.SECONDS));
        } finally {
            context.close();
        }
    }

    static final class CloseSignals
            implements ApplicationListener<ContextClosedEvent> {

        final CountDownLatch closing =
                new CountDownLatch(1);
        final CountDownLatch destroyed =
                new CountDownLatch(1);

        @Override
        public void onApplicationEvent(ContextClosedEvent event) {
            closing.countDown();
        }

        @PreDestroy
        void destroy() {
            destroyed.countDown();
        }
    }
}
~~~

The code uses **`AnnotationConfigApplicationContext`**, with Spring's annotation processors and **`jakarta.annotation.PreDestroy`**. When the context closes normally, the callback is invoked on the managed bean.

**Limitation:** this test does not simulate `SIGKILL` or a JVM crash, nor does it measure exact shutdown duration. It proves the Spring lifecycle mechanism. Do not claim `@PreDestroy` runs on every failure path, such as partially initialized beans that were never fully registered.

### 8.2. Why call close twice in the test?

The first call is the subject of the assertions. In **`finally`**, calling close again guarantees cleanup if setup or an assertion throws. Normal context `close` is designed to handle already-closed contexts, though this pattern is not advice to call `close` repeatedly in business code.

If a test owns multiple external resources, each resource still needs an appropriate cleanup policy outside the context.

## 9. @Scheduled: wait for a real tick, not one cycle via sleep

An unstable test:

~~~java
Thread.sleep(500);
assertTrue(jobCounter.get() > 0);
~~~

Things it fails to prove:

- Whether the bean was registered with **`@EnableScheduling`**.
- Whether a tick actually ran or leftover state came from an earlier test.
- Whether the task threw an exception or was delayed by the scheduler.
- Whether 500 ms is enough in CI.

A fixture with a **`CountDownLatch ticked`** counted down inside the **`@Scheduled`** method is far clearer:

~~~java
@Component
class ScheduledTickProbe {

    final CountDownLatch ticked = new CountDownLatch(1);

    @Scheduled(fixedDelay = 100)
    public void tick() {
        ticked.countDown();
    }
}
~~~

This is a **snippet** requiring imports, a bean in a context with **`@EnableScheduling`**, and a configured scheduler. Corresponding test:

~~~java
assertTrue(
        probe.ticked.await(3, TimeUnit.SECONDS),
        "Scheduled task never executed");
~~~

**This signal verifies the task executed at least once**. It does not prove `fixedDelay` equals exactly 100 ms or test all concurrency interactions.

If you need to verify execution counts, use **`CountDownLatch(N)`**, a blocking queue collecting events, or an observer with sequences. Never use multiple sleeps to count ticks over a short interval and label it exact scheduling verification.

### 9.1. On fixedRate and fixedDelay

- **`fixedRate`** schedules at a target cadence, yet actual execution can lag on busy machines.
- **`fixedDelay`** measures the delay after the previous execution completes.
- **`cron`** depends on clocks, timezones, calendars, and scheduler semantics.

Never assume the scheduler is a real-time clock. For date/time business logic, decouple schedule calculation from actual scheduling and use **`Clock.fixed(...)`** when testing business time.

### 9.2. Do not let old jobs affect new tests

With **`@SpringBootTest`**, `ApplicationContext` may be cached across tests. A singleton latch or counter may already have been triggered by an earlier test.

Prefer:

- Fresh fixtures per test when possible.
- Clearing/resetting state via controlled thread-safe APIs.
- **`@DirtiesContext`** when a fresh context is required and its cost is acceptable.
- Never running tests sharing a scheduler/fixture in parallel without isolation.

Never reuse one static latch across all test methods expecting it to reset automatically.

## 10. Startup events: awaiting ApplicationReadyEvent properly

In Spring Boot, there are distinct milestones:

~~~text
SpringApplication.run()
     |
     +-- Environment prepared
     +-- ApplicationContext refresh
     +-- ApplicationStartedEvent
     +-- ApplicationRunner / CommandLineRunner
     +-- ApplicationReadyEvent
            |
            v
      App ready on normal startup flow
~~~

If a test must ensure runners have finished, observe **`ApplicationReadyEvent`** via a listener registered **before starting the application**.

Do not register a listener **after `ApplicationReadyEvent` has already fired** and then await a latch: Spring events are not a replay log by default. A listener attached after the event milestone may wait until timeout even though the app is already ready.

### 10.1. Short example for startup events

~~~java
CountDownLatch ready = new CountDownLatch(1);

SpringApplication app =
        new SpringApplication(MyApplication.class);
app.addListeners(
        (ApplicationListener<ApplicationReadyEvent>) event ->
                ready.countDown());

ConfigurableApplicationContext context =
        app.run(args);

try {
    assertTrue(ready.await(2, TimeUnit.SECONDS));
} finally {
    context.close();
}
~~~

This is an **integration snippet**, requiring imports for `SpringApplication`, `ApplicationListener`, `ApplicationReadyEvent`, `ConfigurableApplicationContext`, `CountDownLatch`, `TimeUnit`, `assertTrue`, and definitions for `MyApplication`/`args`. The listener is registered **before `app.run`**. Because **`run()` returning cleanly has typically already emitted `ReadyEvent`**, the latch captures it and `await` returns immediately.

For **`@SpringBootTest`**, the context is usually built before the test method runs. If you only need beans ready for injection, do not attach a post-startup listener expecting an old `ReadyEvent`; inspect state/beans directly or attach a test listener at the appropriate bootstrap hook.

### 10.2. Ready does not mean all background tasks have finished

**`ApplicationReadyEvent`** indicates the startup phase succeeded; it does not guarantee:

- All `@Scheduled` tasks have run.
- All `@Async` tasks submitted by runners have finished.
- Remote services remain online.
- Message consumers have drained every queued message in the broker.
- HTTP clients have completed all retries.

If a specific post-Ready task must finish, use a **completion signal dedicated to that task**.

## 11. Asynchronous HTTP with Spring MVC and MockMvc

Spring MVC supports handlers returning **`Callable`**, **`DeferredResult`**, or `CompletableFuture`. MockMvc tests must distinguish:

- **The request started async mode**.
- **The async result completed**.
- **Async dispatch produced the final HTTP response**.

Example testing pattern:

~~~java
MvcResult pending = mockMvc.perform(
        get("/async/report"))
        .andExpect(request().asyncStarted())
        .andReturn();

pending.getAsyncResult(3000);

mockMvc.perform(asyncDispatch(pending))
        .andExpect(status().isOk())
        .andExpect(content().string("done"));
~~~

**This is a snippet for a Spring MVC test with `MockMvc`, `/async/report` endpoint, and static imports** for `MockMvcRequestBuilders`/`ResultMatchers` already set up. It is not a complete source file for section 6's console project; running it standalone requires **`spring-boot-starter-web`** and a controller.

**`getAsyncResult(3000)`** waits up to roughly three seconds instead of `Thread.sleep`. After completion, **`asyncDispatch(...)`** verifies the final response. Never treat the response right after `andExpect(asyncStarted)` as the completed HTTP response.

### 11.1. Do not equate MVC async with @Async as identical

Spring MVC async processing and **`@Async`** service methods can use different executors and completion models. Both require awaiting completion, yet tests must observe the right layer:

- Service async: **`Future`/`CompletableFuture`** from the service.
- MVC async: **async result and dispatch**.
- WebFlux/Reactor: **`Publisher`/`StepVerifier`** or appropriate reactive waiting.
- Streaming/SSE: **event completion/cancellation semantics**; unbounded streams have no "self-completion" under normal deadlines.

Never force every async style into a single latch when the framework provides standard completion APIs.

## 12. Awaitility when conditions can only be observed by polling

Sometimes production code exposes no `Future` or event callback. For example, a background consumer updates database state, and the test can only read the final state.

In such cases, **`Awaitility`** provides eventual assertions with timeouts and polling:

~~~java
await()
        .atMost(5, TimeUnit.SECONDS)
        .pollInterval(50, TimeUnit.MILLISECONDS)
        .untilAsserted(() ->
                assertEquals("DONE", statusRepository.find(id)));
~~~

This snippet requires the **`Awaitility`** library, matching imports, and initialized repository and `id`. If the project lacks Awaitility, add the test dependency:

~~~xml
<dependency>
    <groupId>org.awaitility</groupId>
    <artifactId>awaitility</artifactId>
    <version>4.2.2</version>
    <scope>test</scope>
</dependency>
~~~

In larger projects, use managed, compatible BOM versions; the example pins a concrete version for the Maven demo.

**Difference from `Thread.sleep`:** Awaitility stops early as soon as the condition holds, rather than always waiting a fixed duration. The timeout is the upper bound of the polling loop.

### 12.1. Is polling always best?

No. When you control the code/fixture and can emit a **`CountDownLatch`/`CompletionStage`** signal, event-based waiting typically provides:

- Lower latency.
- Less load on databases/HTTP services.
- Clearer event tracing.
- Fewer races with state reset between polls.

Polling fits when **the system exposes only observable state** without reliable callbacks. Choose bounded poll intervals and `atMost` limits.

### 12.2. Can you poll non-thread-safe data?

No. Reading a plain field repeatedly creates no memory synchronization. When state is written by another thread, use `Atomic`/`volatile`/locks or read a storage system with an appropriate consistency contract.

A polling test with accurate timing can still fail visibility checks if state is not published thread-safely.

## 13. Mockito verify(timeout): using it in the right scenarios

Mockito offers verification with timeouts:

~~~java
verify(mockListener, timeout(2000).times(1))
        .onCompleted("42");
~~~

This snippet requires `mockListener` and Mockito static imports. It helps when code invokes a callback on a mock without returning a `Future`. However:

- It verifies **the interaction occurred**, not other side effects.
- **`timeout(...)`** and **`after(...)`** have different semantics; never treat them as equivalent.
- The call may occur before the business job finishes committing.
- Negative assertions like "callback never fires" over a finite time window do not prove the event can never occur later.

Whenever you can use **`Future.get(timeout)`** or a **`CountDownLatch`** tied to the real completion milestone, they usually express the contract more cleanly.

## 14. JUnit @Timeout and assertTimeoutPreemptively

### 14.1. Two deadline layers should coexist

For an async test:

- **Local wait timeout:** `latch.await(2s)`, `future.get(3s)`. It pinpoints exactly which milestone did not complete.
- **Whole-test watchdog:** **`@Timeout(10s)`**. It prevents another bug from hanging the test forever outside awaited points.

Example:

~~~java
@Test
@Timeout(10)
void completedWithinDeadline() throws Exception {
    assertEquals("DONE", future.get(3, TimeUnit.SECONDS));
}
~~~

This is a test snippet assuming `future` was initialized earlier. `@Timeout` defaults to **seconds** if no unit is specified. Complete tests still require separate resource cleanup.

**Do not merely wrap a test containing `Thread.sleep(1000)` in `@Timeout(30)` and call flakiness fixed.** A total deadline prevents hangs, yet creates no synchronization with events.

### 14.2. assertTimeout vs. assertTimeoutPreemptively

JUnit provides:

~~~java
assertTimeout(
        Duration.ofSeconds(3),
        () -> operation());
~~~

and:

~~~java
assertTimeoutPreemptively(
        Duration.ofSeconds(3),
        () -> operation());
~~~

These are snippets assuming `operation()` and static imports. Critical difference:

- **`assertTimeout`** runs the code on the current thread and checks elapsed time; it **does not forcibly interrupt hung code** just because the deadline passed.
- **`assertTimeoutPreemptively`** runs the executable on another thread so it can report timeout early, yet **switches thread context** and interruption does not necessarily stop underlying tasks.

### 14.3. Risk with Spring @Transactional and ThreadLocal

Spring test-managed transactions typically bind transaction state via the test thread's **`ThreadLocal`**.

If `assertTimeoutPreemptively` wraps a database operation in a `@Transactional` test:

- Code inside the executable runs on **a different thread**.
- That other thread does not carry the test thread's transaction context.
- Operations may **actually commit** instead of rolling back with the test transaction.
- The test can look green while leaving persisted data behind.

JUnit 5 documentation specifically warns about **preemptive timeouts and transactional tests**.

**Recommendation:** for Spring transactional tests, prefer **`Future.get(timeout)`** or **`CountDownLatch.await(timeout)`**; use **`@Timeout(..., threadMode=SAME_THREAD)`** to preserve thread-sensitive context where appropriate. If a separate thread must be used, design explicit transaction/data cleanup and never assume rollback crosses thread boundaries automatically.

### 14.4. @Timeout does not automatically cancel everything behind the scenes

When a test times out:

- JUnit may interrupt the test thread per `threadMode`.
- Other Futures/workers may still be running.
- HTTP calls may not stop automatically if they ignore interrupts/cancellation.
- Spring's context cache may keep schedulers alive for subsequent tests.

Use **`finally`** to release latches, cancel tasks where supported, stop executors, and close resources per ownership.

## 15. Test timeouts vs. business logic timeouts

A system typically has multiple deadlines:

~~~text
Test await timeout             : 2 seconds
Fake worker gate timeout       : 5 seconds
Business API timeout           : 10 seconds
HTTP client connect timeout    : 1 second
Whole-test watchdog            : 12 seconds
CI process/build timeout       : several minutes
~~~

Numbers are illustrative, not optimal settings. What matters is that **each deadline has a clear purpose**.

For example, if a test awaits task completion with a 3s timeout while production code uses a 30s timeout for a real external API, the test may be unsuitable for testing the production timeout. In unit tests, fakes/stubs should control completion; production timeouts must be verified with dedicated clock/fake/network tests.

**Test timeouts must be generous enough to avoid false failures on slow CI scheduling, yet finite to fail within reasonable time.** You do not need to wait the full production threshold in every unit test.

### 15.1. Measuring latency is not checking completion

If the goal is performance, use benchmarks/profiling with warm-ups and statistics, rather than tests asserting "must finish within 20 ms" on a shared CI runner.

Correctness tests should verify **eventual completion within a reasonable test budget**. Benchmarks separately measure distributions/throughput/percentiles.

### 15.2. Use a shared deadline across multiple wait steps

If a test has three sequential awaits of 10s each, total wait can reach 30s. Sometimes you want one **shared deadline**:

~~~java
long deadline = System.nanoTime()
        + TimeUnit.SECONDS.toNanos(5);

long remaining = deadline - System.nanoTime();
if (remaining <= 0
        || !started.await(remaining, TimeUnit.NANOSECONDS)) {
    throw new AssertionError("Start deadline exceeded");
}
~~~

This is a snippet. Across multiple milestones, recompute `remaining` from **`System.nanoTime()`** before each await. Use **`nanoTime`** for durations/timeouts since it is the proper monotonic clock, never **`System.currentTimeMillis()`** which risks wall-clock shifts.

Mind overflow when adding very large deadlines; for short multi-second test spans, the arithmetic above is suitable.

## 16. Handling failures inside workers properly

### 16.1. Do not fire the success latch too early

Broken code:

~~~java
done.countDown();
repository.save(entity);
~~~

If the test awaits `done` and reads the repository, it can run **before `save` completes**. The signal sits at the wrong milestone.

Better:

~~~java
repository.save(entity);
done.countDown();
~~~

These are illustrative snippets. If `save` is asynchronous and returns a `Future`, await actual **commit/completion** before firing `done`. If a transaction only commits after the method returns, `countDown` inside the method can still **arrive before transaction commit**; in that case use transaction synchronization or a completion signal reflecting the true commit point.

**Placing the signal at the exact milestone matters more than which latch type you pick.**

### 16.2. Always signal completion on failure too

If a test only has a `done` latch and the worker throws an exception before `countDown`, the test waits until timeout without knowing the root cause.

One pattern:

~~~java
CompletableFuture<String> completion =
        new CompletableFuture<>();

executor.execute(() -> {
    try {
        String result = performWork();
        completion.complete(result);
    } catch (Throwable ex) {
        completion.completeExceptionally(ex);
    }
});
~~~

This snippet requires `executor`, `performWork`, and imports. `CompletableFuture` propagates both success and failure; tests can call **`get(timeout)`** and inspect **`ExecutionException.getCause()`**.

With latches, use **`finally`** to fire `done` and store exceptions in an **`AtomicReference<Throwable>`**, then assert both status and error. Never merely await and declare success.

### 16.3. Future.get timeout does not automatically interrupt the worker

If:

~~~java
future.get(2, TimeUnit.SECONDS);
~~~

throws `TimeoutException`, the task may still be running. For an `ExecutorService` `Future`, try **`future.cancel(true)`** during cleanup if the task supports interruption.

**Specifically, `CompletableFuture.cancel(true)`** must not be relied upon to interrupt underlying operations; completion cancellation and thread cancellation are two distinct concepts. Apply cancellation policies suited to each specific API/library.

### 16.4. Preserve the interrupt flag

A task awaiting a latch should handle interruption as:

~~~java
try {
    gate.await();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Interrupted", ex);
}
~~~

If a task receives an interrupt during shutdown and you swallow it, it may keep running or report inaccurate state. Preserve the interrupt flag or propagate per the method contract.

Tests must also recognize **`await(timeout)`** can throw `InterruptedException`, not merely return `false`.

## 17. Negative assertions and race conditions

Testing "the event must happen" can wait on a latch. However, "the event absolutely never happens" is a much stronger claim: you cannot prove infinity merely by waiting 100 ms.

For example:

~~~java
assertFalse(done.await(100, TimeUnit.MILLISECONDS));
~~~

proves only that **`done` did not fire within a 100 ms window**. It does not prove the event won't happen afterward.

### 17.1. Replace clock-based negative tests with gates

With a task intentionally waiting on **`release`**, the test knows the worker hasn't been released and can assert the Future is incomplete:

~~~java
assertTrue(started.await(2, TimeUnit.SECONDS));
assertFalse(future.isDone());
release.countDown();
assertEquals("DONE", future.get(3, TimeUnit.SECONDS));
~~~

The absence of completion at that point is backed by **causal control** in the fixture, not merely "slept 100 ms and saw nothing".

Still, if the worker has another completion path or times out internally, the assertion can fail; fake designs must make all completion paths explicit.

### 17.2. Checking order of multiple events with BlockingQueue

When verifying milestones **`STARTED`**, **`COMMITTED`**, **`CLOSED`**, push events into a queue:

~~~java
BlockingQueue<String> events =
        new LinkedBlockingQueue<>();

events.offer("STARTED");
events.offer("COMMITTED");

assertEquals(
        "STARTED",
        events.poll(2, TimeUnit.SECONDS));
assertEquals(
        "COMMITTED",
        events.poll(2, TimeUnit.SECONDS));
~~~

This is an illustrative snippet requiring imports. In practice, `offer` calls sit inside different business callbacks; the test does not emit both itself as in this snippet. **`BlockingQueue.poll(timeout)`** returns `null` when the deadline expires, so assertions should include helpful messages.

Queues let you observe **event ordering** rather than just a completed boolean.

## 18. Test isolation: preventing state leaks from earlier tests

Flakiness also stems from shared fixtures:

- A `CountDownLatch` already counted down to 0 in an earlier test.
- Static `AtomicInteger`s not reset between tests.
- `@SpringBootTest` caching the same `ApplicationContext` repeatedly.
- `@Scheduled` beans continuing to run between test methods.
- An executor from a previous test left unshut down.
- `@Async` jobs writing to the repository after a test finished.
- Parallel tests sharing ports, topics, queues, or database rows.

To reduce risk:

1. **Give each test its own latch/Future/gate** whenever possible.
2. With `@SpringBootTest`, avoid keeping long-lived mutable test state in singleton beans.
3. Use **`@DirtiesContext`** only when a fresh context is truly needed, given startup cost.
4. Use unique IDs for each test's data.
5. Clean up via `finally` and bounded shutdowns.
6. When running parallel tests, audit shared resources and framework synchronization.
7. Never increase sleep to "stabilize" a real race.

### 18.1. Test fixtures must also have internal timeouts

Even when the test uses `await(3s)`, if a fixture worker awaits a gate **without a timeout** and the test aborts, that thread can outlive the test into the next one. Therefore the main examples combine:

- Timeout when the **test awaits**.
- Timeout when the **fake worker awaits**.
- **`finally` release**.
- Executor `shutdown`/`awaitTermination`.

These are distinct protective layers, not redundant duplication.

### 18.2. Test cleanup must not mask the original error

If a main assertion fails while `finally` also throws a cleanup error, you may only see the cleanup exception. For complex resources, use **`try-with-resources`**, JUnit teardown, or collect suppressed exceptions per policy.

Never omit cleanup altogether out of fear of masking exceptions. Thread/socket leaks break subsequent tests and are harder to debug.

## 19. Do Java 21 virtual threads change the principles?

No. Virtual threads on Java 21 still require synchronization and completion signals; they do not make **`Thread.sleep(1000)`** reliable waiting.

You can use **`Executors.newVirtualThreadPerTaskExecutor()`** and **`Future.get(timeout)`** just like platform executors, though this is a **Java 21+ API** and will not compile on Java 17.

Differences that can affect tests:

- Virtual threads are always daemon threads, so they may not keep the JVM alive when `main` exits.
- Never rely on thread names to determine work completed.
- Having more virtual threads can surface rare races more readily.
- Waiting on latches/Futures still needs deadlines and interrupt semantics.
- In a background Spring Boot app enabling virtual threads, JVM lifetime must be managed separately; a unit test with a non-daemon test runner does not prove the production process stays alive.

**Never turn test timeouts into an assumption that the JVM keeps all virtual tasks running to completion**. Completion tests and process lifetimes are two separate contracts.

## 20. What to measure in CI

To distinguish scheduling flakiness from code bugs:

- Which test timed out and **at which milestone** (`STARTED`, `COMPLETED`, or `CLEANED_UP`).
- Actual timeout value and test retry count (if any).
- Worker stack trace/root cause from `Future`/`CompletionStage`.
- Thread dumps when tests hang, executor queue depth, or active counts.
- Spring `ApplicationContext` startup/shutdown event markers.
- How many worker threads remain alive after teardown.
- Context startup time and post-submit latency.
- Service/container readiness signals when tests include integrations.

A timeout awaiting `started` can mean the task was never scheduled or the `@Async` bean wasn't invoked. A `future.get` timeout after `started` fired can mean the task is stuck on a gate, I/O, deadlocked, or failed to signal completion. Failure messages should distinguish these two cases.

### 20.1. Do not use whole-test retries as the first fix

JUnit repeated tests, CI reruns, and retries can diagnose instability, yet can also **hide race conditions**. Prioritize finding missing signals and bounding timeouts/state first. If retries are later needed for a flaky integration dependency, back the policy with clear rationale and metrics.

## 21. Anti-patterns to avoid

### 21.1. Fixed Thread.sleep then reading state

Wrong because it wastes time on fast machines and falls short on slow ones. Use event signals or eventual assertions with timeouts.

### 21.2. CountDownLatch.await() without a timeout

Can hang forever if the task never calls `countDown`. Use `await(timeout, unit)` and assert the boolean result.

### 21.3. Future.join() without a deadline when completion is uncertain

Can wait indefinitely. Prefer `get(timeout, unit)` when tests need bounded waits.

### 21.4. Firing the done signal before side effects finish

Tests can read data before commit. Place the signal at the true completion milestone.

### 21.5. Calling countDown only on success

Worker errors make tests wait until timeout without seeing the exception. Use `CompletableFuture` exceptional completion or store the cause and signal in `finally`.

### 21.6. Using assertTimeoutPreemptively in @Transactional tests

Another thread can lose Spring's thread-bound transaction context, causing unintended commits. Prefer `@Timeout SAME_THREAD` and local bounded waits.

### 21.7. Skipping cleanup when assertions fail

Leaves blocked workers, open sockets, or stale contexts behind. Use `finally` to release/cancel/close within deadlines.

### 21.8. Directly testing new AsyncService() and claiming @Async doesn't work

By default `@Async` relies on a Spring proxy. Tests must use an injected bean or unit-test pure logic separately.

### 21.9. Waiting for ApplicationReadyEvent with a listener registered after Ready

Past events are not replayed by default. Register listeners before bootstrap or inspect current state.

### 21.10. Treating @Scheduled ticks as an exact clock

Scheduling can drift. Test "it ran" with signals, and test business time with `Clock`/fake clocks.

### 21.11. Replacing one big sleep with 10 small sleeps

Manual polling may shorten waits yet still requires visibility, deadlines, and proper conditions. Use Awaitility or signals with clear semantics.

### 21.12. Treating "didn't happen in 100 ms" as "never happens"

Only proves a finite window. Use gates/control flow wherever possible.

### 21.13. Raising timeouts excessively to eliminate flakiness

Masks deadlocks or missing signals. Timeouts must be finite and justified; identify which milestone caused the wait.

### 21.14. Cancelling CompletableFuture and assuming the worker stopped

Future cancellation does not always interrupt underlying tasks. Rely on real executor/I/O cancellation/termination semantics.

### 21.15. Running parallel tests sharing one singleton latch

State from another test can open the latch. Create isolated fixtures or enforce explicit isolation.

## 22. Checklist for writing stable async tests

- [ ] Clearly identify the milestone under test: `STARTED`, `COMPLETED`, or `CLEANED_UP`.
- [ ] Never use `Thread.sleep` as proof work finished.
- [ ] When a `Future` exists, use `get(timeout)` and check result/error.
- [ ] When callbacks/events exist, use `CountDownLatch` with `await(timeout)`.
- [ ] When only observable state exists, use bounded eventual assertions like Awaitility.
- [ ] Signals fire at the exact business milestone, never before commit/flush/close.
- [ ] Worker failures propagate back to tests rather than disappearing into logs.
- [ ] Every wait has a clear timeout failure message.
- [ ] Have `@Timeout` as an outer bound around local waits.
- [ ] Never casually use preemptive timeouts in `@Transactional`/`ThreadLocal`-dependent tests.
- [ ] Tests exercising `@Async` call through a Spring proxy.
- [ ] Fake dependencies can be released in `finally`.
- [ ] Executors/connections/contexts are closed and awaited within bounds.
- [ ] Mutable fixtures are never unintentionally shared via context cache/parallel tests.
- [ ] `SmartLifecycle.stop(Runnable)` calls its callback when stopping finishes.
- [ ] Shutdown tests prove the close `Future` completes, not merely that stop was requested.
- [ ] Startup tests do not wait for events emitted before the listener registered.
- [ ] Scheduler tests observe real ticks rather than guessing with sleep durations.
- [ ] MVC async tests check both async result and `asyncDispatch`.
- [ ] On CI flakiness, record the timed-out milestone and root cause instead of just increasing sleep.
- [ ] Tests leave no background threads/resources running after completion.

## 23. Self-check questions

**Question 1.** Why is `Thread.sleep(1000)` an unreliable way to test async completion?

**Answer:** It merely waits a fixed duration without knowing whether the task started or finished; CI may be slower than assumed while fast machines waste time.

**Question 2.** What does `CountDownLatch.await(2, SECONDS)` return on expiration?

**Answer:** `false`; when enough `countDown` calls arrive, it returns `true`.

**Question 3.** Does `Future.get(2, SECONDS)` automatically cancel the task on expiration?

**Answer:** No. It throws `TimeoutException`; the task may still be running and needs separate cancellation/cleanup.

**Question 4.** Why is a `STARTED` latch insufficient to prove a job `COMPLETED`?

**Answer:** The task may be waiting on I/O, a gate, or may have thrown an error after `started`. You need a completion stage or a `done` signal at the right milestone.

**Question 5.** Does awaiting a latch provide better memory visibility than `Thread.sleep`?

**Answer:** Yes. `CountDownLatch` establishes a happens-before relationship between actions before `countDown` and actions after a successful `await`.

**Question 6.** If an `@Async` method is called via `this.method()` inside the same bean, is the test verifying async execution via proxy?

**Answer:** No. Self-invocation normally bypasses the Spring AOP proxy. Call through an injected bean.

**Question 7.** In `SmartLifecycle`, when should `stop(Runnable)`'s callback be invoked?

**Answer:** When the component has actually finished stopping; forgetting the callback can stall context shutdown until the phase timeout.

**Question 8.** If `ContextClosedEvent` was received, is `@PreDestroy` guaranteed to be done?

**Answer:** Not yet. `ContextClosedEvent` signals the context is closing; destruction is a separate milestone that must be observed independently.

**Question 9.** What risk does `assertTimeoutPreemptively` pose in Spring `@Transactional` tests?

**Answer:** The executable runs on another thread, potentially losing the `ThreadLocal` transaction context and committing data unintentionally.

**Question 10.** When should Awaitility be used instead of `CountDownLatch`?

**Answer:** When the system exposes only final observable/pollable state with no reliable completion callback.

**Question 11.** Does a listener registered after `ApplicationReadyEvent` automatically receive the past event?

**Answer:** Not under the default event multicaster mechanism. Register before startup or inspect current state.

**Question 12.** Why must latches be released in a test's `finally` block?

**Answer:** If an assertion fails early, workers will not stay blocked forever; reduces thread leaks, hung contexts, and cross-test interference.

**Question 13.** Can you prove an event never happens by having `await(100ms)` return `false`?

**Answer:** No, that only proves it did not happen within that finite window.

**Question 14.** When testing async HTTP with MockMvc, why is `asyncDispatch` needed?

**Answer:** A request at `asyncStarted` does not yet have its final response; `asyncDispatch` lets you assert status/body after the async result completes.

## 24. Summary

Good async testing does not ask **"how many milliseconds should I wait to be safe?"** — it asks:

1. **Which milestone must I verify?** Did the task start, complete, fail, or clean up?
2. **What signal does that milestone emit?** `CountDownLatch`, `Future`/`CompletionStage`, callback, event, or pollable state.
3. **What is the wait deadline?** Every `await`/`get` and the entire test must be bounded.
4. **If the test fails midway, who releases/cancels/closes resources?**
5. **Does the signal reflect real completion?** Never `countDown` before commit or stop callback.

With **Spring Boot 3.3/Java 17+**, use **`Future.get(timeout)`** for `@Async`, **`CountDownLatch.await(timeout)`** for startup/shutdown/scheduled signals, **`SmartLifecycle.stop(Runnable)` callbacks** to verify async stopping, and **`ApplicationContext.close()`** when testing destruction. Use **JUnit `@Timeout`** as an outer watchdog, avoiding preemptive thread mode when tests depend on transactions/`ThreadLocal`.

These principles make tests faster when work finishes early, provide meaningful errors when work fails to run, and reduce flakiness caused by speed differences between developer machines and CI.

## 25. Official documentation

- Java SE 17 — CountDownLatch and happens-before: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- Java SE 17 — Future.get(timeout) and cancellation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- Java SE 17 — CompletableFuture: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Spring Boot 3.3 — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html
- Spring Framework 6.1 — SmartLifecycle API and stop callback: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework — Async Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework — MockMvc Async Requests: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework/async-requests.html
- JUnit 5 User Guide — Timeouts and Preemptive Timeout Pitfalls: https://docs.junit.org/5.10.3/user-guide/index.html
- Awaitility documentation: https://github.com/awaitility/awaitility