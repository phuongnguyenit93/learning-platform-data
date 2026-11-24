# Future Allows Waiting for Results or Receiving Errors When Work Finishes

## 1. Why Is Future Needed?

In Java and Spring applications, work can be delegated to a worker thread so the caller can continue processing other tasks. However, the caller still needs to know **whether the task has finished, what the result is, and whether an error occurred**. The `java.util.concurrent.Future<V>` interface provides a **handle representing the result of a computation that may not have completed yet**.

Business example: a request submits a report generation task to a thread pool. Afterward, the system wants to retrieve the report path, detect failures, or wait no longer than a specified deadline. Instead of treating task submission as already successful, the code holds onto `Future<Report>` and reads it at the point where the result is actually needed.

After this lesson, you will:

- Understand `Future<V>` in the thread pool model and distinguish **task acceptance**, **task completion**, **success**, **failure**, and **cancellation**.
- Use `get()`, `get(timeout, unit)`, `isDone()`, `isCancelled()`, and `cancel(...)` accurately.
- Catch `ExecutionException` to extract the **cause as the original task error**, distinguishing it from `InterruptedException`, `TimeoutException`, and `CancellationException`.
- Build standalone **Java 17+** examples with deterministic output and test timeout/cancellation without guessing thread scheduling.
- Use `Future` through the JDK's `ExecutorService.submit(...)` and Spring's `AsyncTaskExecutor.submit(...)`/`@Async`.
- Know when `Future` is enough, when to use `CompletableFuture` to compose asynchronous steps, and the risks of waiting on a Future inside the same pool.

**Versions:** The JDK examples use Java 17+, and the standalone Spring example uses Spring Framework 6.1.3 and Java 17+. They demonstrate stable APIs without depending on Java 21 virtual threads.

## 2. The Model: Task Runs Elsewhere, Future Is the Handle

`Future<V>` is neither a worker thread nor the work itself. It is an object allowing the caller to track the state of a computation submitted to an executor.

~~~text
Caller thread                            Executor / worker
      |                                          |
      | submit(Callable<V>)                      |
      |----------------------------------------->|
      |<------ Future<V> ------------------------|
      |                                          |
      | do other work                            | run call()
      |                                          |
      | future.get()                             |
      | ------ wait if not yet completed ------> |
      |                                          |
      |<------- value V / exception -------------|
~~~

From the moment the `Future` is received until `get()` is called, the caller can continue processing independently. If `get()` is called **immediately**, the caller may block until the worker completes; concurrency benefits may still exist, but it does not necessarily improve latency in the way you expect.

### Four Situations to Distinguish

| Situation | `isDone()` | `isCancelled()` | `get()` |
| --- | --- | --- | --- |
| Task is still queued or running | `false` | `false` | May **block** |
| Task completed successfully | `true` | `false` | Returns `V`; `Runnable` returns `null` |
| Task completed with an exception | `true` | `false` | Throws `ExecutionException`, cause is the execution error |
| Task was cancelled successfully | `true` | `true` | Throws `CancellationException` |

**Important:** `isDone() == true` only means the task has **ended in some way**, which could be success, exception, or cancellation. Never use `isDone()` as business proof of success.

A task can be **rejected right at the submit step** when the pool is overloaded or shut down. In that case, the submit call may throw an exception **before returning a Future**: there is no `Future` to wait for a result on. This is an **admission** error, not an error inside an accepted task.

## 3. Core Future API in Java 17

`Future<V>` belongs to package `java.util.concurrent`; `V` is the expected result type. The key methods in the Java 17 API are:

| Method | Behavior | Notes |
| --- | --- | --- |
| `V get()` | Waits if needed, then retrieves the result | Can block indefinitely if the task never completes |
| `V get(long timeout, TimeUnit unit)` | Waits up to the given duration, then retrieves the result | Throws `TimeoutException` if not completed within the deadline |
| `boolean isDone()` | Indicates the Future has ended, including failure/cancellation | **Does not confirm success** |
| `boolean isCancelled()` | Indicates it was cancelled | `false` does not mean the task succeeded |
| `boolean cancel(boolean mayInterruptIfRunning)` | Attempts to cancel the computation | Must consider the implementation and the task's cooperation with interrupts |

Signature examples:

~~~java
// API signatures for explanation; not a standalone class.
V get() throws InterruptedException, ExecutionException;

V get(long timeout, TimeUnit unit)
        throws InterruptedException, ExecutionException, TimeoutException;

boolean isDone();
boolean isCancelled();
boolean cancel(boolean mayInterruptIfRunning);
~~~

**Version note:** This is the Java 17-compatible method set. Newer JDK versions add state-access utilities such as `state()`/`resultNow()`/`exceptionNow()`, but do not write Java 17 code relying on those newer methods.

### 3.1. `get()` Returns the Result on Success

~~~java
// Fragment: executor is a configured ExecutorService.
Future<Integer> answer = executor.submit(() -> 21 * 2);
Integer result = answer.get(); // 42 on success
~~~

`submit(Callable<Integer>)` accepts a value-returning lambda; `Future<Integer>` lets you retrieve the result. `get()` **blocks the calling thread** if not yet complete. If the task is already complete, the method returns immediately. `get()` does not execute the task in place of the worker.

### 3.2. `submit(Runnable)` Still Returns a Future Without a Payload

~~~java
// Fragment: Runnable returns no data.
Future<?> saved = executor.submit(() -> saveRecord());
Object result = saved.get(); // null if executed successfully
~~~

Here `saveRecord()` is an undefined application function, so the snippet is not standalone. With `Runnable`, the future tracks completion and errors; the successful result is typically `null`. If you need to return a business value, use `Callable<T>` or `ExecutorService`'s `submit(Runnable, result)` overload.

Do not confuse with `execute(Runnable)`: the `execute` method accepts work but has a `void` return type, so it does not directly provide a Future for tracking.

### 3.3. `get(timeout, unit)` Bounds Caller Wait Time

~~~java
// Fragment: retrieve result within at most 2 seconds of waiting.
String data = future.get(2, TimeUnit.SECONDS);
~~~

If 2 seconds pass and the Future is still not complete, the caller receives `TimeoutException` and can switch to a fallback or timeout response. **The task is not automatically cancelled just because `get` timed out**; it may still be running and causing side effects. To cancel, the application must make a separate decision (for example `future.cancel(true)` when appropriate) and understand that cancellation does not guarantee stopping all I/O in every implementation.

### 3.4. Happens-Before Relationship and Shared Results

The JDK 17 `Future` Javadoc specifies: actions taken by the asynchronous computation **happen-before** actions following the corresponding `Future.get()` in another thread. Thus, after a successful `get()`, the caller has a synchronization relationship to observe results published through task completion. However, if the task continues running or you share mutable objects across multiple other threads, other data-race issues must still be solved through thread-safe design; do not treat `Future` as a lock protecting every variable.

## 4. Future.get Exceptions and How to Handle Them

Each exception tells a different story:

| Exception | Appears when | Typical action required |
| --- | --- | --- |
| `ExecutionException` (checked) | The task ran and threw an exception | Read `getCause()`, log/classify business errors |
| `InterruptedException` (checked) | The waiting thread was interrupted | Restore `Thread.currentThread().interrupt()` if not propagating |
| `TimeoutException` (checked, timed get only) | Caller waited past the deadline, Future not yet complete | Fallback/return timeout; decide separately whether to cancel task |
| `CancellationException` (unchecked) | Future was cancelled | Cancellation handling path, do not read value as success |

### `ExecutionException` Wraps the Root Error, Not Replacing It

Suppose a task throws `IllegalStateException("invalid-state")`. If the task was accepted via `submit(Callable)`, the exception is stored in the Future. The caller calls `get()` and receives `ExecutionException`. Use `ex.getCause()` to obtain the root error:

~~~java
try {
    Integer value = future.get();
    use(value);
} catch (ExecutionException ex) {
    Throwable rootCause = ex.getCause();
    reportFailure(rootCause);
}
~~~

This is a **fragment**, requiring application variables/functions, imports, and handling/declaring `InterruptedException`. Do not log only the `ExecutionException` line while ignoring the stack trace/cause. At the same time, do not always blindly "rethrow cause" without classification: connection errors, validation errors, and programming bugs may require different policies.

### `InterruptedException` Does Not Mean the Worker Failed

`get()` throws `InterruptedException` when **the waiting caller thread** is interrupted. That **does not by itself prove** the task in the worker failed or stopped. If you are not responsible for handling interrupts at the current layer, you can propagate the exception or restore the interrupt flag and exit the processing path:

~~~java
try {
    return future.get();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Waiting thread interrupted", ex);
}
~~~

This is a fragment inside a method with an appropriate return type that also needs to handle `ExecutionException`; not a standalone class. Restoring the interrupt is important because many blocking APIs clear the interrupt flag when throwing `InterruptedException`. Do not automatically keep waiting indefinitely and swallow that signal.

### `TimeoutException` Is Not `ExecutionException`

When `future.get(1, TimeUnit.SECONDS)` expires, the caller can receive `TimeoutException` even if the worker finishes **a millisecond later**. Do not read `isDone()` at a later moment and conclude backward that the earlier timeout was impossible: the two actions occurred at two different points in time. A timeout is the result of **waiting too long**, not a conclusion that the task definitely failed.

## 5. Complete Java 17+ Example: Results and Errors

Save the program below as `FutureBasicsDemo.java`. It submits a succeeding task, a failing task, and a `Runnable`, then reads each Future in turn. It does not depend on Spring so you can understand the foundational contract first.

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class FutureBasicsDemo {

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<Integer> ok = pool.submit(() -> 21 * 2);

            Future<Integer> failed = pool.submit(
                    (Callable<Integer>) () -> {
                        throw new IllegalStateException("invalid-state");
                    });

            Future<?> sideEffect = pool.submit((Runnable) () -> { });

            System.out.println("value=" + ok.get());

            try {
                failed.get();
                System.out.println("unexpected-success");
            } catch (ExecutionException ex) {
                Throwable cause = ex.getCause();
                System.out.println("error="
                        + cause.getClass().getSimpleName()
                        + ":" + cause.getMessage());
            }

            System.out.println("runnableValue=" + sideEffect.get());
            System.out.println("okDone=" + ok.isDone());
            System.out.println("failedDone=" + failed.isDone());

        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac FutureBasicsDemo.java
java FutureBasicsDemo
~~~

**Output printed by the program:**

~~~text
value=42
error=IllegalStateException:invalid-state
runnableValue=null
okDone=true
failedDone=true
~~~

**Explanation:**

1. `ok` represents a `Callable<Integer>` returning `42`, so `ok.get()` is `42`.
2. `failed` is a task that **was accepted** but threw `IllegalStateException`; `failed.get()` throws `ExecutionException` with a cause containing `invalid-state`.
3. `sideEffect` is a `Runnable` returning no payload; a successful `get()` returns `null`.
4. Both `ok.isDone()` and `failed.isDone()` are `true`. This is clear proof that **done does not mean success**.
5. `shutdown()` and `awaitTermination()` clean up the pool, leaving no non-daemon workers behind. If cleanup times out, the example calls `shutdownNow()` to request termination.

The code only prints from **main** after waiting on the Futures, not from multiple workers concurrently, so output line order is stable even though the **execution** order of the three tasks is not guaranteed.

## 6. Complete Java 17+ Example: Timeout Does Not Automatically Cancel the Task

The second example uses two `CountDownLatch` instances: `started` confirms the task has begun; `release` holds the task until main explicitly allows it to finish. That way, timeout can be verified **without relying on `Thread.sleep()` or machine speed**.

Save as `FutureTimeoutDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class FutureTimeoutDemo {

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> pending = pool.submit(() -> {
                started.countDown();
                release.await();
                return "ready";
            });

            started.await(); // task has started

            try {
                pending.get(100, TimeUnit.MILLISECONDS);
                System.out.println("unexpected-value");
            } catch (TimeoutException ex) {
                System.out.println("timed-out=true");
            }

            System.out.println("doneBeforeRelease=" + pending.isDone());

            release.countDown();
            System.out.println("value=" + pending.get(5, TimeUnit.SECONDS));

        } finally {
            release.countDown(); // avoid holding worker if caller errors
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac FutureTimeoutDemo.java
java FutureTimeoutDemo
~~~

Output:

~~~text
timed-out=true
doneBeforeRelease=false
value=ready
~~~

The first `get(100, MILLISECONDS)` times out because the task is still waiting on `release`. At that point `isDone()` is `false`, proving that **caller timeout does not terminate the task**. After `release.countDown()`, the worker proceeds, and `get(5, SECONDS)` returns `"ready"`.

In a real system, if a task is making an HTTP call or JDBC query instead of `CountDownLatch.await()`, a `Future.get` timeout still does not automatically stop the HTTP request or DB query. Set explicit timeouts for downstream I/O, bound concurrency, and consider cancelling the task according to the business contract.

## 7. Cancellation: Future Can Cancel, but Is Not an Absolute Kill Switch

`future.cancel(boolean mayInterruptIfRunning)` requests cancellation of the task; the outcome depends on state and implementation:

- If the Future has already completed, `cancel(...)` usually returns `false` and does not alter the result.
- If the task has not started yet and cancellation succeeds, the task should not run.
- If the task is running, `cancel(true)` allows the implementation to attempt to **interrupt the worker thread** when the worker is known. The task must cooperate with interrupts and the cancellation capabilities of underlying I/O.
- `cancel(false)` does not request interrupting a running worker; that does not prove all side effects will stop occurring. Never treat `cancel` as a transaction rollback.
- After a Future is cancelled successfully, `isCancelled()` and `isDone()` can both be `true`; `get()` throws `CancellationException`.

To observe clearly, use the JDK's `FutureTask` through an executor. Save as `FutureCancelDemo.java`:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class FutureCancelDemo {

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> task = pool.submit(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return "interrupted";
                }
                return "finished";
            });

            started.await(); // task is running, no result yet
            boolean requested = task.cancel(true);

            System.out.println("cancelRequested=" + requested);
            System.out.println("isCancelled=" + task.isCancelled());
            System.out.println("isDone=" + task.isDone());

            try {
                task.get();
                System.out.println("unexpected-value");
            } catch (CancellationException ex) {
                System.out.println("get=CancellationException");
            }

        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac FutureCancelDemo.java
java FutureCancelDemo
~~~

Stable expected output with `ExecutorService.newSingleThreadExecutor()` and the task held by a latch:

~~~text
cancelRequested=true
isCancelled=true
isDone=true
get=CancellationException
~~~

Note: the line `cancelRequested=true` shows **the cancellation request was accepted by the Future**, not a guarantee that all side effects that already happened or are about to happen in the task are undone. In the example, the task waits at an interrupt-supporting point; a task executing code that never checks interrupts or an I/O library that does not respond to interrupts may not stop right away. When a task must not leave a business transaction half-done, design cancellation and transactions explicitly.

### Difference of CompletableFuture.cancel

`CompletableFuture` **implements Future**, but the JDK specifies that `CompletableFuture.cancel(boolean)` treats cancellation as an **exceptional completion**; the `mayInterruptIfRunning` flag has no effect for directly interrupting the underlying task like a regular `FutureTask`. Do not switch from `FutureTask` to `CompletableFuture` and assume the underlying execution cancellation mechanism behaves identically.

## 8. Spring Integration: AsyncTaskExecutor Returns Future

In Spring, the basic `org.springframework.core.task.TaskExecutor` has `execute(Runnable)` and returns `void`. The `AsyncTaskExecutor` interface extends it with `submit` overloads:

~~~java
// API signatures, not a standalone runnable file:
Future<?> submit(Runnable task);
<T> Future<T> submit(Callable<T> task);
~~~

Spring Framework 6.1.3 `AsyncTaskExecutor` supports these two methods. `ThreadPoolTaskExecutor` is a common implementation for managing worker threads and queues. If you declare a variable of type `TaskExecutor`, you **cannot call `submit` through that static type**; inject `AsyncTaskExecutor` or an appropriate implementation.

### 8.1. Standalone Spring Framework 6.1.3 Example (Maven)

The following example runs with `main`, **without needing a Spring Boot server or `@EnableAsync`**, because it calls `submit` directly on an initialized executor. Structure:

~~~text
spring-future-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SpringFutureDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-future-demo</artifactId>
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
                    <mainClass>demo.SpringFutureDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/demo/SpringFutureDemo.java`:

~~~java
package demo;

import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class SpringFutureDemo {

    public static void main(String[] args) throws Exception {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("spring-future-");
        pool.initialize();

        try {
            AsyncTaskExecutor executor = pool;

            Future<String> ok = executor.submit(() -> "report-ready");
            Future<Integer> bad = executor.submit(
                    (Callable<Integer>) () -> {
                        throw new IllegalArgumentException("invalid-id");
                    });

            System.out.println("springValue=" + ok.get(5, TimeUnit.SECONDS));

            try {
                bad.get(5, TimeUnit.SECONDS);
                System.out.println("unexpected-value");
            } catch (ExecutionException ex) {
                Throwable cause = ex.getCause();
                System.out.println("springCause="
                        + cause.getClass().getSimpleName()
                        + ":" + cause.getMessage());
            }

        } finally {
            pool.shutdown();
        }
    }
}
~~~

In the `spring-future-demo` directory, run:

~~~bash
mvn -q compile exec:java
~~~

Output printed by the Java program (excluding separate Maven logs):

~~~text
springValue=report-ready
springCause=IllegalArgumentException:invalid-id
~~~

Here Spring's `ThreadPoolTaskExecutor` accepts both the succeeding task and the failing task. Both Futures are handles to the submitted work. `get` waits for completion and provides either the value or `ExecutionException` wrapping the cause of the error. `pool.shutdown()` cleans up the manually created executor; in a real Spring application, register the pool as a singleton bean so the container manages its lifecycle.

### 8.2. Rejection Happens Before Any Future Exists

`AsyncTaskExecutor.submit(...)` can throw `TaskRejectedException` **right at the submission point** if the pool is shut down, the queue is full, and no more workers can be expanded. In that case, `Future<T> future = executor.submit(...)` **does not finish assigning the variable**. Do not call `future.get()` looking for an exception when no Future was ever returned.

~~~java
// Fragment in a service having an executor variable of type AsyncTaskExecutor.
try {
    Future<String> future = executor.submit(() -> "ok");
    return future;
} catch (org.springframework.core.task.TaskRejectedException ex) {
    // Record metric/log for overload or lifecycle shutdown.
    throw ex;
}
~~~

This snippet is not standalone; it assumes the enclosing method returns `Future<String>`. Spring's `TaskRejectedException` extends the JDK's `RejectedExecutionException`. It differs from `ExecutionException` of a task that **was already accepted**.

## 9. Spring @Async: Returning Future from Business Methods

Spring `@Async` allows a method to be invoked asynchronously via an interceptor/proxy when `@EnableAsync` is enabled and bean/caller conditions are met. The method can declare a return type of `Future<T>` or `CompletableFuture<T>` instead of `void`. The caller receives a Future representing the asynchronous method invocation.

Configuration example in a Spring application with component scanning enabled (the classes are **architectural fragments**, not a standalone `main` project):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class ReportAsyncConfig {
    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("report-");
        return executor;
    }
}
~~~

Business method inside another bean:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @Async("reportExecutor")
    public CompletableFuture<String> generate(String id) {
        String result = "report:" + id;
        return CompletableFuture.completedFuture(result);
    }
}
~~~

Example of a **Spring-managed** caller with `ReportService` injected:

~~~java
CompletableFuture<String> result = reportService.generate("A42");
String value = result.get(5, TimeUnit.SECONDS); // "report:A42"
~~~

The caller snippet is a fragment; it needs `reportService` declared/injected, `TimeUnit` imported, and checked exceptions declared or handled. The Spring proxy submits the call to the executor and returns a Future to the caller. When the worker runs the target method, the method can return `CompletableFuture.completedFuture(...)` as a vehicle to supply the value; **the Future the caller receives from the proxy** is what represents the asynchronous work.

**Frequently forgotten conditions:**

- Place `@EnableAsync` on a configuration class and ensure the service is a Spring-managed bean.
- Call from another bean **through the Spring proxy**. Self-invocation (`this.generate(...)` inside the same service) usually **bypasses the proxy** in the default `AdviceMode.PROXY` mode.
- `@Async("reportExecutor")` selects the executor by exact name; if you use the wrong name or the caller creates the service with `new`, behavior will not match expectations.
- Do not place `@Async` on methods declared **inside a `@Configuration` class**: the Spring Javadoc explicitly states this case is not supported. Let the configuration declare the executor and put business methods in a service.
- With `@Async void`, the caller **has no Future** to read exceptions; Spring supports `AsyncUncaughtExceptionHandler` or configured logging. When error control is needed, prefer Future/CompletableFuture-returning APIs where appropriate.

## 10. Comparing Future and CompletableFuture

`CompletableFuture<T>` **is an implementation of `Future<T>`** and also implements `CompletionStage<T>`. It has APIs for composing asynchronous processing, such as `thenApply`, `thenCombine`, `thenCompose`, and `exceptionally`.

| Need | Plain `Future<T>` | `CompletableFuture<T>` |
| --- | --- | --- |
| Wait for task and retrieve result | `get()` | `get()` or `join()` |
| Check done / cancel | Yes | Yes |
| Wait with timeout | `get(timeout, unit)` | `get(timeout, unit)`; also has dedicated timeout APIs |
| Combine multiple tasks without blocking-waiting each Future | No chaining APIs in the interface | Has `thenCombine`, `thenCompose`, `allOf` |
| Recover a value when a task fails | Manual `try/catch` around `get` | Has `exceptionally`/`handle` |
| How exceptions appear on `join()` | No `join()` | `CompletionException` (unchecked) on failure |
| `cancel(true)` behavior | Depends on `Future` implementation | Does not use `mayInterruptIfRunning` flag to interrupt task per `CompletableFuture` contract |

If the problem only needs "submit work, occasionally wait for the result," `Future` fits well. If you need **non-blocking multi-step composition**, `CompletableFuture` is usually a better fit.

In Spring Framework 6.0+, `AsyncTaskExecutor` also has:

~~~java
// Illustrative signatures (Spring 6.0+):
CompletableFuture<Void> submitCompletable(Runnable task);
<T> CompletableFuture<T> submitCompletable(Callable<T> task);
~~~

Important point: the `submitCompletable` overloads **only exist starting in Spring Framework 6.0**. With Spring 5.x, you can use `CompletableFuture.supplyAsync(..., taskExecutor)` or `runAsync(..., taskExecutor)`, but note that `Supplier` does not declare checked exceptions like `Callable`. Do not mix up Java 17 APIs, Spring versions, and interface types when upgrading projects.

### How Does Combining Two Futures Differ from CompletableFuture?

With two plain `Future<Integer>` instances, you typically must call `get()` to retrieve each result:

~~~java
Future<Integer> a = executor.submit(() -> 10);
Future<Integer> b = executor.submit(() -> 20);
int sum = a.get() + b.get(); // 30
~~~

This is a fragment with `executor` of type `ExecutorService` and an enclosing method handling checked exceptions. Both tasks are submitted **before waiting**, so they can run in parallel, yet `get()` still blocks the caller.

With `CompletableFuture`, you can describe the combination step to run when both complete:

~~~java
CompletableFuture<Integer> a =
        CompletableFuture.supplyAsync(() -> 10, executor);
CompletableFuture<Integer> b =
        CompletableFuture.supplyAsync(() -> 20, executor);

CompletableFuture<Integer> sum =
        a.thenCombine(b, Integer::sum);
~~~

This is also a fragment, requiring `executor` to be an `Executor` and `CompletableFuture` imports. If you need to preserve concurrency control in Spring, pass an **explicit executor** instead of accidentally using `ForkJoinPool.commonPool()`. `sum` can be returned to another layer without blocking where it is created.

## 11. Avoiding Self-Inflicted Thread Pool Deadlocks When Waiting on Future

A common mistake is **task A running on a single-worker pool**, then A submits task B to the same pool and calls `B.get()`. A holds the only worker waiting for B; B has no worker to run. This is a form of **thread-starvation deadlock**.

~~~text
Pool with exactly 1 worker:
  worker runs task A
      |
      +-- submit(task B) to same pool
      |
      +-- B.get() --> A is blocked
                      |
                      +-- B is in the queue,
                          but the worker is still held by A
~~~

Do not "solve" this by changing `get()` to `get(timeout)` and considering the issue gone: timeout only lets A eventually stop waiting, but the architecture still lacks workers under the same pattern. Consider splitting dependent steps into asynchronous composition, using an appropriate executor, avoiding blocking workers on child tasks within the same small pool, or decomposing the processing flow.

Additionally, repeatedly calling `isDone()` in a `while(!future.isDone())` loop without sleeping/waiting is **busy-wait**, wasting CPU. Use `get` at the boundary where data is needed, `CompletableFuture` callbacks, or purpose-built synchronization APIs.

## 12. Checklist for Applying Future in Real Applications

1. **Choose a result-returning API:** `ExecutorService.submit(Callable)` or `AsyncTaskExecutor.submit(Callable)` returns `Future<T>`; `execute` provides no handle.
2. **Submit independent tasks before waiting:** avoid serializing by calling `get()` immediately after each `submit` unnecessarily.
3. **Set wait limits at boundaries requiring SLAs:** use `get(timeout, unit)` instead of waiting indefinitely on unreliable remote I/O; configure separate timeouts at HTTP/JDBC.
4. **Separate error paths:** `TaskRejectedException` at **submit** differs from `ExecutionException` at **get**. Do not let one broad catch mask both causes.
5. **Inspect the cause:** log useful context and `getCause()` rather than only the `ExecutionException` message.
6. **Handle interrupts:** if catching `InterruptedException` without propagating it, restore the interrupt flag.
7. **Do not treat done as success:** `isDone` can be true when a task failed or was cancelled.
8. **Respect cooperative cancellation:** `cancel(true)` only attempts to interrupt when the implementation supports it; side effects, transactions, and I/O do not roll back automatically.
9. **Do not discard Futures of important tasks:** if the caller never calls `get` or registers an observation mechanism, exceptions inside the task may go unhandled.
10. **Monitor pool and queue:** backlog, worker count, task duration, timeout, and rejection rate help detect overload; do not make the queue unbounded just to hide errors.
11. **Avoid waiting inside the same small pool:** holding a worker to wait for a dependent Future can stall pool progress.
12. **In Spring, ensure async actually runs:** service managed by the context, calls go through the proxy, `@EnableAsync`, and the exact executor name.

### Self-Check Questions

**Question 1.** Does `future.isDone()` equal to `true` prove the task succeeded?  
**Answer:** No. `isDone` is true when completed normally, when an error is thrown, or when cancelled.

**Question 2.** When a `Callable` throws `IllegalArgumentException` in the worker after the task was accepted, what does `future.get()` report?  
**Answer:** `ExecutionException`; the original error is inside `getCause()`.

**Question 3.** `future.get(100, MILLISECONDS)` throws `TimeoutException`. Is the task stopped immediately?  
**Answer:** No. Only **the caller's wait** timed out; the task can still keep running.

**Question 4.** If the caller is interrupted while waiting, does that tell us the worker has failed?  
**Answer:** Not necessarily. `InterruptedException` belongs to the waiting thread; handle the interrupt, do not infer worker state from it.

**Question 5.** Spring `TaskExecutor` only declares `execute`. How do you obtain a `Future<String>` from a task returning a String?  
**Answer:** Use `AsyncTaskExecutor` or an appropriate implementation and call `submit(Callable<String>)`. With `@Async`, you can declare return type `Future<String>` or `CompletableFuture<String>` on a method of a Spring-processed bean.

**Question 6.** Why doesn't `future.get()` catch the executor rejecting a task at submission time?  
**Answer:** If rejected, `submit` already threw an exception **before returning a Future**; it must be caught at the submission site.

**Question 7.** Why can two `Future`s submitted to a single-worker pool deadlock if the first task waits on `get` of the second task?  
**Answer:** The first task holds the sole worker; the second task sits in the queue with no worker to execute it, so the wait can never be satisfied.

**Question 8.** How does `CompletableFuture` differ from plain `Future` in a way that helps multi-step workflows?  
**Answer:** It has `CompletionStage` with composition/callback/error-recovery methods, avoiding blocking the caller at each step.

## 13. Official References

- [Java SE 17 — Future Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): defines `get`, timeouts, exceptions, cancellation, `isDone`, and the happens-before relationship.
- [Java SE 17 — ExecutorService Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`, `shutdown`, and executor lifecycle.
- [Java SE 17 — FutureTask Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html): an implementation allowing Future use with Runnable.
- [Java SE 17 — CompletableFuture Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `CompletionStage`, `join`, chaining, errors, and cancellation.
- [Spring Framework 6.1.3 — AsyncTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html): `submit` returning `Future` and `submitCompletable` (since Spring 6.0).
- [Spring Framework 6.1.3 — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): pool implementation, queue, submit, and TaskRejectedException.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): `@Async`, Future return types, and exception handling.
