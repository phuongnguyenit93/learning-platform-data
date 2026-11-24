# orTimeout() and completeOnTimeout() Do Not Automatically Stop Running Operations

## 1. Why Does the Future Expire While the Task Keeps Running?

When handling asynchronous work in Java or Spring, a `CompletableFuture<T>` typically represents **a result that may arrive in the future**, but it **does not necessarily control the lifecycle of work already submitted to an executor**. This distinction matters when using:

- `orTimeout(long timeout, TimeUnit unit)` — if the future has not completed, completes **that same future** **exceptionally** with `TimeoutException` after the deadline.
- `completeOnTimeout(T value, long timeout, TimeUnit unit)` — if the future has not completed, completes **that same future** **normally** with a fallback value after the deadline.

**Both change how the caller observes the result; neither automatically interrupts the running thread, cancels an HTTP request, stops a database query, or rolls back the task's side effects.** The worker may keep working after the future has timed out or returned a fallback.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish **the state of a `CompletableFuture`** from **the actual state of the underlying computation/I/O**.
2. Explain `orTimeout`, `completeOnTimeout`, `get(timeout)`, `cancel(true)`, and the return values of each API.
3. Understand “first completion wins”: a late result generally does not replace a future already completed by timeout or fallback.
4. Write deterministic Java 17+ programs using `CountDownLatch` to prove the worker is still busy after the future has completed.
5. Apply these concepts with Spring's `ThreadPoolTaskExecutor`, choosing dedicated executors, managing resources, and configuring real I/O timeouts.
6. Avoid production pitfalls: overlapping retries, hiding errors with fallbacks, holding connections too long, exhausting pools, or assuming `CompletableFuture.cancel(true)` interrupted the worker.
7. Test both **timely responses** and **actual resource release**, rather than asserting only on future state.

**Versions:** `orTimeout` and `completeOnTimeout` have existed since **Java 9**, and the examples run on **Java 17+**. The Spring example uses **Spring Framework 6.1.3**; the timeout APIs belong to the JDK, not a Spring-specific feature.

## 2. Four Time Quantities That Are Not the Same

An asynchronous request usually involves at least four distinct intervals:

| Time type | What does it measure? | Typical API / mechanism |
| --- | --- | --- |
| **Caller wait time** | How long the caller waits for the result | `Future.get(timeout, unit)` |
| **Future completion deadline** | When the caller sees a timeout or fallback | `orTimeout` / `completeOnTimeout` |
| **Actual operation duration** | How long HTTP/SQL/file I/O executes | Timeouts of HTTP client, JDBC, SDK, socket, query, driver |
| **Worker/task lifecycle** | Whether the task finished, was interrupted, was cancelled, or still occupies a worker | Executor, `FutureTask`, cooperative interrupt, resource-specific cancellation |

You cannot look solely at Future state and infer that every underlying layer has stopped.

For example, a `Supplier` makes a synchronous API call taking 8 seconds, while `completeOnTimeout("cached", 1, SECONDS)` returns a fallback after 1 second: the caller sees `"cached"`, yet the synchronous HTTP request **can still run for another 7 seconds**. If many such requests arrive, workers and connections can still become exhausted regardless of how fast your API responds.

### Illustrative Timeline

~~~text
t = 0 ms       Caller submits task --> worker starts HTTP call
                 |
t = 1000 ms    orTimeout: Future completes with TimeoutException
                 |         or
                 +------ completeOnTimeout: Future completes with fallback
                 |
                 |        Worker may still be waiting on HTTP/DB
                 |        No automatic interrupt from either API above
                 |
t = 8000 ms    HTTP call finishes, Supplier returns "real" result
                 |
                 +------ Future already timed out / fell back earlier:
                         late result does not overwrite the earlier winning completion
~~~

This timeline illustrates a scenario where the actual operation runs longer than the deadline; it does not mean a thread always runs for a full 8 seconds. With proper I/O-layer timeouts, the worker can finish sooner.

## 3. Java 17 APIs: The Most Important Exact Details

Two instance methods on `java.util.concurrent.CompletableFuture<T>`:

~~~java
// Abbreviated API signatures, not a standalone Java class.
CompletableFuture<T> orTimeout(long timeout, TimeUnit unit);

CompletableFuture<T> completeOnTimeout(
        T value, long timeout, TimeUnit unit);
~~~

The Javadoc of **both** states **returns: this CompletableFuture**. They **do not create a new independent Future** just because their return type is `CompletableFuture<T>`. They schedule an action that attempts to complete **the original object** if it has not completed by the timeout.

### 3.1. `orTimeout()`: Completing with a Timeout Error

~~~java
// Illustrative fragment, assuming future is CompletableFuture<String>.
CompletableFuture<String> timed =
        future.orTimeout(2, TimeUnit.SECONDS);
boolean sameObject = timed == future; // true
~~~

If the task finishes before 2 seconds, the existing normal result or error is preserved. If the timeout wins, the future completes **exceptionally** with `TimeoutException`.

- `future.isDone()` becomes `true`.
- `future.isCompletedExceptionally()` becomes `true`.
- `future.isCancelled()` **does not automatically become true**: timeout is not cancellation.
- `future.join()` typically throws `CompletionException` whose `getCause()` is `TimeoutException`.
- `future.get()` per the `Future` contract throws `ExecutionException` whose cause is `TimeoutException`.
- Actual workers and I/O are not automatically interrupted by this timeout call.

Do not write `catch (TimeoutException ex)` directly around `join()`: `join()` does not declare checked `TimeoutException`; catch `CompletionException` and inspect its cause. `get(timeout, unit)` and `get()` throw different exception types—keep them distinct.

### 3.2. `completeOnTimeout()`: Completing with a Fallback

~~~java
// Illustrative fragment.
CompletableFuture<String> recovered =
        future.completeOnTimeout("cached", 2, TimeUnit.SECONDS);
boolean sameObject = recovered == future; // true
~~~

If the future has not completed after 2 seconds, it completes **normally** with `"cached"`. Then:

- `future.isDone()` is `true`.
- `future.isCompletedExceptionally()` is `false`, because the fallback counts as a **normal successful Future value**.
- `future.join()` returns `"cached"`.
- The `Supplier` may continue processing, accessing the database, or calling other APIs.
- A real result arriving later will not automatically switch `join()` from `"cached"` to the real value.

Because the fallback is treated as success at the future level, **explicitly tag the value's origin in business logic** (e.g., `Result(value, fromFallback)`, metrics, or logs); otherwise calling layers may fail to distinguish fresh data from cached data.

### 3.3. `get(timeout)` Only Limits How Long the Caller Waits

~~~java
// Fragment: bounds the current wait call.
String result = future.get(2, TimeUnit.SECONDS);
~~~

If expired, `get(timeout, unit)` throws **`TimeoutException` in the waiting thread**, without **completing or cancelling the Future**. If the task later produces a successful result, you can still call `future.get()`/`join()` again to obtain the real result.

This is the decisive difference:

| Aspect | `get(2, SECONDS)` | `orTimeout(2, SECONDS)` | `completeOnTimeout("cached", 2, SECONDS)` |
| --- | --- | --- | --- |
| Purpose | Bounds one caller **wait** | Sets deadline to complete Future with error | Sets deadline to complete Future with fallback |
| Returns | Value `T` or throws exception | **Same** `CompletableFuture<T>` object | **Same** `CompletableFuture<T>` object |
| On expiration | Caller receives `TimeoutException` | Future completes exceptionally with `TimeoutException` | Future completes normally with `"cached"` |
| Future `isDone()` after timeout | May still be `false` | `true` | `true` |
| Late real result | **Still retrievable** | Usually does not change already timed-out Future state | Usually does not overwrite winning fallback value |
| Auto-interrupts worker | **No** | **No** | **No** |
| Auto-cancels HTTP/SQL | **No** | **No** | **No** |

**Race note:** If the real result completes right around the timeout, whichever completion operation **wins first** determines the state. Do not write tests assuming two nearly simultaneous events must happen in one fixed order.

## 4. A Timed-Out Future Is Different from a Finished Task

`CompletableFuture` is a mechanism for **value completion** and **stage composition**. `CompletableFuture.supplyAsync(supplier, executor)` submits a task to an `Executor`, yet `CompletableFuture` does not necessarily hold a handle to interrupt, stop, or roll back what the `Supplier` is doing.

In `CompletableFuture`, calls attempting to complete the same future from multiple threads compete: **only one side wins** in normal completion (`complete`, `completeExceptionally`, `cancel`). Once a deadline has completed the future first, a late-finishing worker merely attempts to supply a result to an already completed future; the late value does not overwrite the winning completion.

**The task can still cause side effects after the caller receives a timeout.** For example:

- A transaction/transfer is still sent to a remote service.
- An INSERT/UPDATE statement can still execute even after the HTTP client returned a fallback.
- Memory, sockets, database connections, and executor threads remain held.
- A late-finishing task can trigger logs/metrics or another side effect inside the `Supplier` itself.
- If the caller immediately retries because of the timeout, two operations can **run concurrently**.

Do not treat `future.isDone() == true` as a signal that threads, sockets, and transactions have all finished and resources are freed.

## 5. Standalone Java 17+ Example: Three Timeout Types and One Still-Busy Worker

This is the core experiment of the lesson. We use `CountDownLatch` to **keep the Supplier in a running state** until `main` explicitly unlocks it. This proves `orTimeout` and `completeOnTimeout` complete the Future **while the Supplier is not yet finished**.

The program has three branches:

1. `orTimeout`: Future reports `TimeoutException`, yet the worker is still waiting.
2. `completeOnTimeout`: Future returns `fallback`, yet the worker is still waiting.
3. `get(timeout)`: caller receives `TimeoutException`, yet the Future stays pending and later yields the real result.

Save as `TimeoutDoesNotStopDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class TimeoutDoesNotStopDemo {

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            showOrTimeout(pool);
            showCompleteOnTimeout(pool);
            showTimedGet(pool);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    private static CompletableFuture<String> blockedWork(
            ExecutorService pool,
            CountDownLatch started,
            CountDownLatch release,
            CountDownLatch workerReachedFinally) {

        return CompletableFuture.supplyAsync(() -> {
            started.countDown();
            try {
                release.await();
                return "real";
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return "interrupted";
            } finally {
                workerReachedFinally.countDown();
            }
        }, pool);
    }

    private static void showOrTimeout(ExecutorService pool)
            throws Exception {

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch reachedFinally = new CountDownLatch(1);
        CompletableFuture<String> future = blockedWork(
                pool, started, release, reachedFinally);

        try {
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker did not start");
            }

            boolean same = future.orTimeout(
                    100, TimeUnit.MILLISECONDS) == future;
            System.out.println("orSameFuture=" + same);

            try {
                future.join();
                System.out.println("unexpected-or-success");
            } catch (CompletionException ex) {
                System.out.println("orCause="
                        + ex.getCause().getClass().getSimpleName());
            }

            System.out.println("orWorkerFinishedAtTimeout="
                    + (reachedFinally.getCount() == 0));
        } finally {
            release.countDown(); // release even if the wait branch fails
        }

        if (!reachedFinally.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("worker did not exit");
        }
        System.out.println("orStillExceptional="
                + future.isCompletedExceptionally());
    }

    private static void showCompleteOnTimeout(ExecutorService pool)
            throws Exception {

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch reachedFinally = new CountDownLatch(1);
        CompletableFuture<String> future = blockedWork(
                pool, started, release, reachedFinally);

        try {
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker did not start");
            }

            boolean same = future.completeOnTimeout(
                    "fallback", 100, TimeUnit.MILLISECONDS) == future;
            System.out.println("fallbackSameFuture=" + same);
            System.out.println("fallbackValue=" + future.join());
            System.out.println("fallbackWorkerFinishedAtTimeout="
                    + (reachedFinally.getCount() == 0));
        } finally {
            release.countDown();
        }

        if (!reachedFinally.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("worker did not exit");
        }
        System.out.println("fallbackAfterRealWork=" + future.join());
    }

    private static void showTimedGet(ExecutorService pool)
            throws Exception {

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch reachedFinally = new CountDownLatch(1);
        CompletableFuture<String> future = blockedWork(
                pool, started, release, reachedFinally);

        try {
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker did not start");
            }

            try {
                future.get(100, TimeUnit.MILLISECONDS);
                System.out.println("unexpected-get-success");
            } catch (TimeoutException ex) {
                System.out.println("getTimedOut=true");
            }

            System.out.println("getFutureDoneAtTimeout="
                    + future.isDone());
        } finally {
            release.countDown();
        }

        if (!reachedFinally.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("worker did not exit");
        }
        System.out.println("getValueAfterRealWork=" + future.join());
    }
}
~~~

Compile and run:

~~~bash
javac TimeoutDoesNotStopDemo.java
java TimeoutDoesNotStopDemo
~~~

**Expected output during normal execution:**

~~~text
orSameFuture=true
orCause=TimeoutException
orWorkerFinishedAtTimeout=false
orStillExceptional=true
fallbackSameFuture=true
fallbackValue=fallback
fallbackWorkerFinishedAtTimeout=false
fallbackAfterRealWork=fallback
getTimedOut=true
getFutureDoneAtTimeout=false
getValueAfterRealWork=real
~~~

### Explaining the Determinism of the Example

- `started.await(...)` waits for the exact signal that the worker **has started**; the task then waits on `release`.
- When `main` calls `join()` after `orTimeout` or `completeOnTimeout`, the worker is still held by `release.await()`. Thus it prints `...WorkerFinishedAtTimeout=false`, without needing to guess whether the worker slept long enough.
- `orTimeout` completes the future with an error, so `join()` reports `CompletionException` with cause `TimeoutException`. The worker reaching `finally` after the latch opens **cannot turn that future into a success**.
- `completeOnTimeout` places `"fallback"` into the future itself; when the worker eventually returns `"real"`, `future.join()` is still `"fallback"`.
- `get(100, MILLISECONDS)` only limits that wait attempt; after releasing the worker, the Future was never forced to time out and therefore returns `"real"`.
- Output lines are printed only by **main**, never concurrently from workers, so output does not depend on cross-thread log ordering.
- Each method has a `finally` block opening its latch; `main` calls `shutdown/awaitTermination` to clean up workers. In an environment unable to start a worker within 5 seconds, the program fails fast with a startup error rather than assuming standard results.

**Technical note:** The `workerReachedFinally` latch confirms the `Supplier` **reached `finally`**; right after that, the thread still returns from the lambda and the executor updates completion. Here, checking only needs to prove that at the timeout instant the `Supplier` **had not yet reached `finally`**, without relying on a latch as a Java `Future` work-state publication contract.

## 6. Why Shouldn't You Use Thread.sleep to “Prove” Timeouts?

A simple example often does `Thread.sleep(500)` and then `orTimeout(100, MILLISECONDS)`. That can illustrate the idea, but if tests rely only on print timing or thread scheduling, overloaded CI machines can make ordering unpredictable. Using `CountDownLatch` as above is better because the worker cannot pass the wait point before `main` opens the latch.

In production, timeouts measure **real time** and races between tasks and deadlines definitely occur. Tests should focus on **guaranteed behaviors**: the Future returns a fallback or timeout error when the task has not been released, does not auto-cancel I/O, and the pool is cleanly shut down after the test. Do not assert that a timer always fires at millisecond 100 on the dot.

## 7. Spring Framework: TaskExecutor Does Not Change CompletableFuture Timeout Mechanics

Spring's `ThreadPoolTaskExecutor` manages a `java.util.concurrent.ThreadPoolExecutor`, providing `corePoolSize`, `maxPoolSize`, and `queueCapacity`. You can pass this bean as the `Executor` to `CompletableFuture.supplyAsync(supplier, executor)`.

Key points to remember:

- `orTimeout` and `completeOnTimeout` remain **Java `CompletableFuture` APIs**, carrying no functionality to stop tasks on `ThreadPoolTaskExecutor`.
- They can complete the future **while a Spring worker is still busy waiting on I/O**.
- Returning a faster response to callers does not increase backend capacity: pools and downstream dependencies can still saturate if work keeps running too long.
- `AsyncTaskExecutor.submitCompletable(...)`, available since **Spring Framework 6.0+**, also returns a `CompletableFuture`. When applying a timeout to that future, do not assume the worker running the `Runnable/Callable` was interrupted.
- Base `TaskExecutor` only requires `execute(Runnable)`; `CompletableFuture.supplyAsync(..., taskExecutor)` is valid because `TaskExecutor` extends `Executor`. Do not confuse it with `AsyncTaskExecutor`'s `submitCompletable` overloads.
- With `@Async`, pick the right executor and invoke the method through the Spring proxy; timeouts attached to **the future received by the caller** still need timeouts/cancellation at the business-operation layer.

### 7.1. Standalone Runnable Spring Maven Project

This example uses **Spring Framework 6.1.3** and **JDK 17+**, creating a `ThreadPoolTaskExecutor` as a Spring bean and passing it directly into `supplyAsync`. A `CountDownLatch` holds the worker running to prove `completeOnTimeout` returns a fallback while the worker has not stopped.

Structure:

~~~text
spring-timeout-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SpringTimeoutDemo.java
~~~

Contents of `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-timeout-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.3</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.SpringTimeoutDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Contents of `src/main/java/demo/SpringTimeoutDemo.java`:

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class SpringTimeoutDemo {

    @Configuration
    public static class PoolConfiguration {

        @Bean("ioExecutor")
        public ThreadPoolTaskExecutor ioExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(2);
            pool.setThreadNamePrefix("io-");
            return pool;
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             PoolConfiguration.class)) {

            ThreadPoolTaskExecutor executor =
                    context.getBean("ioExecutor", ThreadPoolTaskExecutor.class);

            CountDownLatch started = new CountDownLatch(1);
            CountDownLatch release = new CountDownLatch(1);
            CountDownLatch workerReachedFinally = new CountDownLatch(1);

            CompletableFuture<String> future =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                            return "remote-result";
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                            return "interrupted";
                        } finally {
                            workerReachedFinally.countDown();
                        }
                    }, executor);

            try {
                if (!started.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("worker did not start");
                }

                future.completeOnTimeout(
                        "cached-result", 100, TimeUnit.MILLISECONDS);

                System.out.println("springFallback=" + future.join());
                System.out.println("springWorkerFinishedAtFallback="
                        + (workerReachedFinally.getCount() == 0));
            } finally {
                release.countDown();
            }

            if (!workerReachedFinally.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker did not exit");
            }

            System.out.println("springResultAfterWork=" + future.join());
        }
    }
}
~~~

Run inside `spring-timeout-demo`:

~~~bash
mvn -q compile exec:java
~~~

Output printed by the Java program:

~~~text
springFallback=cached-result
springWorkerFinishedAtFallback=false
springResultAfterWork=cached-result
~~~

**Why does it differ from the real result?** The `ThreadPoolTaskExecutor` worker was waiting on `release`, while the future already completed with `"cached-result"`. When the worker is released and returns `"remote-result"`, that completion does not overwrite the already-completed future. `context.close()` in `try-with-resources` triggers container cleanup of the executor bean.

**`@EnableAsync` is not needed** in this example: the program calls `CompletableFuture.supplyAsync(..., executor)` directly rather than invoking an `@Async` method through a proxy. Do not confuse configuring an executor bean with Spring automatically picking that executor for `supplyAsync(supplier)` calls **without a second argument**.

This is an experiment with a 100 ms deadline for observation; production must choose deadlines based on actual SLAs, not treat 100 ms as a default for network operations.

## 8. CompletableFuture Timeouts Differ from Real HTTP, Database, and Socket Timeouts

When a `Supplier` performs synchronous I/O such as:

~~~java
// Architectural anti-pattern: remoteClient.fetch(id) is a blocking I/O call.
// Illustrative code only; variables/methods are not defined here.
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> remoteClient.fetch(id), ioExecutor)
        .completeOnTimeout("cached", 1, TimeUnit.SECONDS);
~~~

The caller may receive `"cached"` after 1 second, yet `remoteClient.fetch` can still hold a worker and a connection. You need **deadlines for the actual operation**, for example:

- **HTTP client:** connection timeout and response/read/request timeouts matching the library in use. With `java.net.http.HttpRequest.Builder.timeout(...)`, the request timeout applies to the HTTP request itself; when using other client SDKs, check their API documentation.
- **JDBC/SQL:** query timeout via `Statement.setQueryTimeout(...)` when supported by the driver, transaction/database-side timeouts, and query cancellation policies. `Future.orTimeout` does not issue SQL cancel commands.
- **Synchronous sockets/SDKs:** read/write/overall timeouts, request cancellation capabilities, and behavior when the thread is interrupted vary across libraries.
- **Memory / queues:** bounded pools (`corePoolSize`, `maxPoolSize`, `queueCapacity`), semaphores/rate limits, and admission control prevent the count of “timed-out yet still running” tasks from growing unboundedly.
- **Request lifecycle:** if the caller disconnects or the deadline expires, the system must still decide whether the business operation continues, cooperatively cancels, or is persisted durably.

### Deadline Budgeting Rules

Suppose an API has a 2-second SLA. You should not allow a DB query to run for 30 seconds while the Future returns a fallback after 2 seconds and assume the system freed resources. Account for: queue wait time, connect timeout, read/query timeout, retry budget, and serialization/response time.

**A response-layer timeout does not replace an I/O-layer timeout.** If an operation must genuinely be cancelled, use the primitives provided by the library to cancel the query/request, or design cancellation with an explicit contract. Even with cancellation, the remote service may already have performed side effects; cancellation does not mean rollback.

## 9. If Real Cancellation Is Needed: cancel Is a Request, Not Magic

JDK Java 17's `CompletableFuture.cancel(boolean mayInterruptIfRunning)` is documented as a form of **exceptional completion with `CancellationException`**; the `mayInterruptIfRunning` parameter **is not used to interrupt computation** in `CompletableFuture`.

~~~java
// Illustrative fragment, future is an existing CompletableFuture<T>.
boolean cancelled = future.cancel(true);
boolean flag = future.isCancelled();
~~~

Even if `cancelled` is `true`, that is not enough to claim the running worker stopped. `CompletableFuture` does not necessarily hold a handle to the `Thread`/`FutureTask` executing the `Supplier`.

A `Future<?>` obtained from `ExecutorService.submit(...)` or `AsyncTaskExecutor.submit(...)` may support `cancel(true)` to **attempt to interrupt the worker**, depending on implementation. Still, interruption is a **cooperative signal**, not a guarantee of stopping every socket I/O call, transaction, or side effect.

~~~java
// Fragment: rawExecutor is an existing ExecutorService.
// Must handle/declare InterruptedException and ExecutionException.
Future<String> operation = rawExecutor.submit(() -> remoteCall());
try {
    return operation.get(1, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    operation.cancel(true); // attempt interrupt if implementation supports it
    throw ex;
}
~~~

This is a fragment inside a method with an appropriate return type, imports for `Future`/`TimeoutException`/`TimeUnit`, and an application `remoteCall()` method. `cancel(true)` **does not replace HTTP/DB client timeouts**. If the caller already sent a data-update command, the receiving server may still process it even if the local thread is interrupted.

### Cooperative Cancellation in Custom Code

For tasks with loops you control, you can check `Thread.currentThread().isInterrupted()` or a thread-safe cancellation token and exit in a reasonable time. Still, distinguish:

1. **Future completion deadline** — when the caller gets a result/error.
2. **Cancellation request** — who issues the cancel signal and where it goes.
3. **Worker termination** — whether the executing code actually stopped.
4. **Resource cleanup** — whether connections, transactions, and locks were properly closed/rolled back.

No single `completeOnTimeout` call performs all four responsibilities.

## 10. Avoid Letting Timeouts Hide Late Results and Errors

### 10.1. Late Results Are Not Automatically Written into an Already-Completed Future

If a timeout/fallback won first, a `Supplier` later returning success normally does not change the value the caller sees. This holds for standard `CompletableFuture` completions: **first completion wins**. Likewise, an exception occurring late inside the `Supplier` may no longer be visible through the Future that already completed with a fallback.

If the task matters, do not merely log `future.whenComplete(...)` on a future using `completeOnTimeout` and assume that metric reflects **actual execution duration**. It may run when the fallback triggers, **before the worker finishes**.

To measure actual work, instrument **inside the Supplier** or around the network operation:

~~~java
// Fragment: ioExecutor and remoteClient are existing dependencies.
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(() -> {
            long startedAt = System.nanoTime();
            try {
                return remoteClient.fetch();
            } finally {
                recordOperationDuration(System.nanoTime() - startedAt);
            }
        }, ioExecutor).completeOnTimeout("cached", 1, TimeUnit.SECONDS);
~~~

This is a fragment, not a standalone program; `recordOperationDuration` and `remoteClient` are illustrative only. The metric recorded in `finally` runs when **the real Supplier reaches the end**, unlike the Future deadline metric. If you need to know whether the operation was cancelled, also record status/cancellation from the I/O library.

### 10.2. When You Need to Separate the Operation Future from the Response Future

Because `orTimeout`/`completeOnTimeout` returns **the same Future it was called on**, applying a timeout to `upstream` mutates `upstream` itself.

If you need to keep **an original Future** to observe the real outcome, use `copy()` (available since Java 9) before attaching a timeout to the copy:

~~~java
// Fragment: upstream is a CompletableFuture<String> awaiting the operation.
CompletableFuture<String> response =
        upstream.copy()
                .completeOnTimeout("cached", 1, TimeUnit.SECONDS);
~~~

`response` is a separate Future carrying the deadline. If the fallback wins, it does not turn `upstream` into `"cached"`; `upstream` can still complete with the real value or failure. **However, the copy does not cancel the underlying operation either.** This separates completion semantics, not I/O resource management.

Do not use `obtrudeValue(...)` to forcibly overwrite a timed-out result and treat that as solving late updates; it is a special-purpose API that can create inconsistencies with dependent stages and is not a normal timeout/late-result mechanism.

### 10.3. Multiple Timeouts on the Same Future Can Compete

~~~java
// Fragment illustrating an error-prone configuration.
future.orTimeout(1, TimeUnit.SECONDS);
future.completeOnTimeout("cached", 2, TimeUnit.SECONDS);
~~~

Both calls act on **the exact same future**. If still incomplete and the 1-second timer fires first, the Future has already failed with a timeout; the fallback 2 seconds later **will not turn it into a success**. Do not view them as two independent Futures with separate policies.

If you intend to report a fallback after 1 second while still saving the real result later, keep the original Future and create a **separate response future** or design explicit callbacks, deadlines, and a controlled state machine.

## 11. Production Consequences: Retries, Idempotency, Resource Exhaustion

### 11.1. Retries Overlapping Unfinished Operations

A serious hazard:

1. Caller submits `chargePayment(orderId)`.
2. `completeOnTimeout("pending", 2, SECONDS)` returns `"pending"` while the remote operation is unfinished.
3. Caller mistakenly believes the task stopped and submits again.
4. Two payment requests may now be processing concurrently.

**A timeout does not prove a task failed or rolled back.** For side-effecting operations, use idempotency keys, deduplication, an `"unknown/pending"` state, verification against the source of truth, and reconciliation workflows. Do not blindly retry a side-effecting command just because a Future timed out.

### 11.2. Workers/Connections Stay Held Despite Fast Responses

For instance, an API falls back in 100 ms while the HTTP client still has a 60-second timeout: under steady traffic, tasks that already “returned a response” can still occupy most of the pool, causing **`TaskRejectedException`** when the pool/queue fills up. Therefore, monitoring only completed `CompletableFuture` counts is insufficient; inspect active workers, queue depth, in-flight calls, and real downstream timeouts.

### 11.3. Configuring Timeouts by Budget

- **Deadline at API boundary:** the caller can respond after this milestone, while recording that the operation's completion status is not yet certain.
- **Request/read/query timeouts:** stop waiting on I/O at the library layer that actually controls the operation.
- **Retry budget:** attempt counts, backoff, jitter, idempotency, and overall deadline; avoid retry storms.
- **Concurrency limits:** prevent background operations from piling up indefinitely after callers time out.
- **Shutdown/cancellation:** define which tasks must run to completion, which may be discarded, and how resources are released.

There is no single “universally optimal” timeout value for every system; measure p95/p99 latency, timeout rate, false-fallback rate, queue wait, and downstream load.

## 12. Layer-Appropriate Error Handling Table

| Event | What the Future/caller sees | Layer that must handle it |
| --- | --- | --- |
| Supplier finishes before deadline | Real value | Normal business logic |
| `orTimeout` wins | Future completes exceptionally with `TimeoutException` | Caller/response policy, deadline metrics |
| `completeOnTimeout` wins | Future completes normally with fallback | Fallback labeling, data freshness, alerts |
| `get(timeout)` expires | Caller gets `TimeoutException`, Future **may still be pending** | Caller decides whether to wait again, cancel, or exit |
| Accepted task throws an error | Future may complete exceptionally | `handle`/`exceptionally`, cause classification |
| Executor rejects submission | Error may be thrown **immediately at `supplyAsync/submit`** | Catch around submission, capacity/lifecycle |
| Caller/worker is interrupted | `InterruptedException` at supporting blocking APIs | Restore interrupt flag, cooperative cleanup |
| HTTP client disconnects | Future does not automatically know all resources/remote work must stop | Request lifecycle and cancellation policy |

With `ThreadPoolTaskExecutor`, rejections are typically `TaskRejectedException`, a subclass of JDK's `RejectedExecutionException`. It can happen **before any Future is returned**; `future.exceptionally(...)` cannot handle a call that never returned a Future.

If a task returns `CompletableFuture<T>` and completes exceptionally, `join()` typically throws unchecked `CompletionException` with the original cause; `get()` typically throws checked `ExecutionException`. With `orTimeout`, inspect the cause to distinguish `TimeoutException`, since not every exception is a deadline expiration.

## 13. Testing and Operations Checklist

### 13.1. Testing Both Independent States

1. Use a latch to hold the `Supplier` **unfinished**.
2. Set `orTimeout` and assert the Future fails with `TimeoutException` while **the worker is still waiting on the latch**.
3. Set `completeOnTimeout` in a separate run and assert the Future receives the fallback while the `Supplier` is still waiting.
4. Open the latch and assert the `Supplier` reaches `finally`; the already timed-out/fallback Future **does not change to the late result**.
5. Use `get(timeout)` on a Future without an attached timeout to confirm the Future stays pending, then retrieve the result after opening the latch.
6. Test the branch where the operation completes **before** the deadline to ensure the real result is preserved.
7. Test real exceptions, rejections, interrupts, cancellation, and cleanup; avoid short `sleep` calls followed by absolute millisecond assertions.
8. Verify real connections and workers are released, not just `Future.isDone()`.

### 13.2. Metrics to Monitor

- **Future deadline/fallback rate:** how many responses timed out or used fallback data.
- **Underlying operation duration:** how long HTTP/DB/SDK calls take, including after the response Future completed.
- **In-flight operations, active workers, pool size, queue depth:** work still holding resources.
- **Rejection rate and downstream saturation:** exhausted resources, full queues, or executor shutdown.
- **Late completion / late errors:** operations finishing after the deadline; this metric cannot be derived from an early-completed future.
- **Business correctness:** duplicate operations, idempotency conflicts, and transactions in an unknown outcome state.

### 13.3. Selection Rules

- Use `get(timeout)` if you only want to **bound how long the caller waits** while keeping the original Future able to complete later.
- Use `orTimeout` if the contract wants **the Future itself to transition to failure** at the deadline so callers and dependent stages see the error.
- Use `completeOnTimeout` if the business accepts **returning a fallback value** as the Future's result.
- Use **real I/O timeouts, cancellation APIs, and concurrency limits** when you need to free resources, prevent late side effects, or reduce thread-pool pressure.
- Use **a copy or separate response Future** if you want to observe the operation's real result without letting a timeout overwrite upstream state.

## 14. Common Mistakes

1. **“`orTimeout` interrupts the thread when it expires.”** False. It completes the `CompletableFuture` with an error; the worker may keep running.
2. **“`completeOnTimeout` stops HTTP first, then returns fallback.”** False. It only completes the Future with a value if the deadline wins.
3. **“`future.get(timeout)` also sets the Future's state to timed out.”** False. It only limits a single caller wait.
4. **“`completeOnTimeout` returns a new Future and leaves the old Future untouched.”** False. The Javadoc states **returns this CompletableFuture**.
5. **“If the Future `isDone`, the worker and connection are definitely released.”** False when timeout/fallback completed the Future before the operation finished.
6. **“With a fallback, there is no need to log late task errors.”** False. Exceptions in the `Supplier` can happen after the Future already received a fallback; you must observe the real operation.
7. **“`cancel(true)` on CompletableFuture is guaranteed to interrupt the worker.”** False. The `mayInterruptIfRunning` flag does not control interruption in this implementation.
8. **“Attaching multiple timeouts to the same Future creates independent branches.”** False. Instance calls mutate the same object.
9. **“Increasing the thread pool solves everything.”** False. Downstream HTTP/SQL calls can keep running too long, exhausting connections and multiplying load.
10. **“Retrying after a timeout is definitely safe because the old attempt stopped.”** False. You need idempotency and transaction-state verification.
11. **“If the Future's `whenComplete` ran, the real operation has finished.”** False when timeout/fallback happens before `Supplier` completion.
12. **“Switching to `@Async` makes every timeout automatically interrupt the operation.”** False. Spring's async executor does not change `CompletableFuture`'s timeout contract.

## 15. Self-Check Questions

**Question 1.** `orTimeout(1, SECONDS)` completes the Future with `TimeoutException`. Is the SQL query inside the `Supplier` guaranteed to have stopped?  
**Answer:** No. Future completion does not automatically send an SQL cancel command. You need query timeouts/cancellation at the database/JDBC layer.

**Question 2.** `completeOnTimeout("cached", 1, SECONDS)` wins, and later the `Supplier` returns `"fresh"`. What does `future.join()` return?  
**Answer:** `"cached"`, because the Future already completed normally with the fallback; the late result does not overwrite the earlier completion.

**Question 3.** `future.get(1, SECONDS)` throws `TimeoutException`, and the Future has no `orTimeout` attached. Can you keep waiting and get the real result?  
**Answer:** Yes, if the task completes afterward; timed `get` does not complete or cancel the Future.

**Question 4.** Which object do `orTimeout` and `completeOnTimeout` return?  
**Answer:** **The same `CompletableFuture` instance they were called on**, not a copy.

**Question 5.** `future.isDone()` is true right after `completeOnTimeout`. Can you conclude the worker is no longer active?  
**Answer:** No. `isDone` only reflects the Future; the worker may still hold a socket, DB connection, or continue executing side effects.

**Question 6.** Does `CompletableFuture.cancel(true)` guarantee interrupting the `Supplier`?  
**Answer:** No. Java 17 Javadoc states `mayInterruptIfRunning` has no effect for controlling `CompletableFuture` processing.

**Question 7.** If you need to preserve the real result after a timeout while letting the caller wait at most 1 second, what are simple options?  
**Answer:** You can use `get(1, SECONDS)` to bound the wait, or create `upstream.copy().completeOnTimeout(...)` to separate the response Future from upstream. Neither **automatically cancels the task**.

**Question 8.** Why is a metric counting completed Futures insufficient to detect overload?  
**Answer:** Futures may have completed early via deadline/fallback even though real operations still occupy workers and connections; you must measure underlying in-flight work, queues, and resource usage.

## 16. Official References

- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `orTimeout`, `completeOnTimeout` (returns `this`), `copy`, `cancel`, completion semantics, and `join`.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get(timeout)`, `cancel`, `isDone`, interrupts, and result observation.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): task submission, `shutdown`, `Future`, and executor lifecycle.
- [Java SE 17 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): HTTP request-level timeouts for the Java HTTP client.
- [Java SE 17 — Statement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html): `setQueryTimeout` and driver handling of query timeouts.
- [Spring Framework 6.1.3 — AsyncTaskExecutor](https://www.springframework.org/spring/docs/6.1.3/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html): `submitCompletable` (since Spring 6.0), `Future`, and rejection.
- [Spring Framework 6.1.3 — ThreadPoolTaskExecutor](https://www.springframework.org/spring/docs/6.1.3/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): thread pool configuration, queues, exceptions, and lifecycle.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): choosing Spring `TaskExecutor`, `@Async`, pool management, and task handling.
