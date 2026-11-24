# ExecutionException, CompletionException, and Root Cause

## 1. Why does a business error appear under a different exception name?

When Java work runs via `ExecutorService`, `CompletableFuture`, or Spring `@Async`, an error occurring **in the worker** is usually not thrown directly onto the **calling thread's** stack. Instead, the error is recorded as the failed state of a `Future`. When the caller retrieves the result or composes stages, the API reports failure using a **wrapper exception**.

The two most important wrappers:

- **`ExecutionException`**: typically encountered when calling `Future.get()`, `CompletableFuture.get()`, or `get(timeout, unit)` and the computation failed. This is a **checked exception**.
- **`CompletionException`**: typically encountered when calling `CompletableFuture.join()`, `getNow(...)`, or using `CompletionStage` chains where a stage completed exceptionally. This is an **unchecked exception**.

For example, suppose a worker encounters `IllegalStateException("database unavailable")`. The caller may observe:

~~~text
Future.get()
  └── ExecutionException
        └── cause: IllegalStateException("database unavailable")

CompletableFuture.join()
  └── CompletionException
        └── cause: IllegalStateException("database unavailable")
~~~

Both paths can describe **the exact same root error**, rather than two different business errors. You need to inspect **`getCause()`** and the entire cause chain to understand the actual reason. Do not trigger an alert just from seeing `ExecutionException` and conclude that the executor is broken.

**Key takeaway:** the wrapper describes the *asynchronous result propagation mechanism*; the inner cause typically describes the *business or technical condition that led to failure*. However, do not blindly strip all wrappers: sometimes an application-layer exception carries meaning and must be preserved in logs.

## 2. Failure model of an asynchronous task

### 2.1. Errors occur in the worker, observed on the caller

~~~text
Caller thread                           Worker in pool
-------------                           ------------------
future = executor.submit(task)  ----->  runs task
                                                |
                                                +-- throw SQLException /
                                                |   IllegalStateException
                                                |
                                                +-- Future records failure

future.get() -------------------------->  Future completed exceptionally
      |
      +-- throw ExecutionException(cause)
      |
      +-- caller handles or translates error to domain/API
~~~

If the caller uses `CompletableFuture.join()`, the error path typically goes through `CompletionException`, not `ExecutionException`. Code calling `get` can still **block waiting** until the worker finishes; the wrapper only surfaces at the moment the caller observes the failed state.

Clearly distinguish **submission exceptions** from **execution exceptions**:

- **Submission rejected**: a `RejectedExecutionException` (or `TaskRejectedException` via Spring `TaskExecutor`) may appear immediately upon submitting the task. In that case there may not even be a Future to wait on.
- **Task accepted and then fails**: the error is typically stored inside the `Future`/`CompletableFuture` and surfaces when `get`, `join`, or a callback observes the error.
- **Task silently dropped by a policy**: a Future may **never complete** if the task neither ran nor was cancelled; calling `get()` indefinitely will not necessarily yield any wrapper.

Do not use a single `catch (ExecutionException)` to handle every thread pool issue: rejection, cancellation, timeout, and interruption have different error paths.

### 2.2. Throwable hierarchy and cause chain

Relevant classes in the JDK:

~~~text
Throwable
  └── Exception
       ├── InterruptedException              (checked)
       ├── TimeoutException                  (checked)
       ├── ExecutionException                (checked wrapper)
       └── RuntimeException
            ├── CompletionException          (unchecked wrapper)
            └── CancellationException        (unchecked)
~~~

Example:

~~~java
Throwable outer = new CompletionException(
        new ExecutionException(
                new IllegalStateException("connection lost")));
~~~

This is an **illustrative snippet** requiring `import java.util.concurrent.*;`. The cause chain here contains **two wrappers**. Calling `outer.getCause()` only once will still show `ExecutionException`. To interpret the root error, you must walk further through appropriate wrappers.

Not every `Throwable` has a `getCause()`. An exception may have no cause, may have suppressed exceptions, or may have a domain-meaningful cause. Therefore a helper should have a **clear stopping condition**, rather than always looping to the deepest `Throwable` and losing intermediate layers.

## 3. ExecutionException: the contract of Future.get()

### 3.1. When does it occur?

`Future.get()` waits until the task finishes, then:

1. **Success**: returns the value.
2. **Worker failed**: throws `ExecutionException`, with `getCause()` representing the computation's error.
3. **Future was cancelled**: throws `CancellationException`, not `ExecutionException`.
4. **Waiting thread was interrupted**: throws `InterruptedException`.
5. **Using the `get(timeout, unit)` overload and the wait expires**: throws `TimeoutException`.

`ExecutionException` is a checked exception; Java code must catch or declare it. Example:

~~~java
try {
    String result = future.get(3, TimeUnit.SECONDS);
    consume(result);
} catch (ExecutionException ex) {
    Throwable computationError = ex.getCause();
    reportFailure(computationError);
}
~~~

This is an **illustrative snippet**, omitting `future`, `consume`, `reportFailure`, as well as the branches handling `InterruptedException`, `TimeoutException`, and `CancellationException`. Production code must handle the full contract of `get(timeout)`.

**An important point:** `ExecutionException` indicates the computation failed; it is not itself the `SQLException`, `IllegalArgumentException`, or domain exception. Extract the cause to identify the root reason, but **keep the wrapper in exception logs** if you need visibility into the caller-worker boundary.

### 3.2. Future from ExecutorService and CompletableFuture

Both forms can deliver errors via `ExecutionException` when the caller invokes `get()`:

~~~java
Future<String> f1 = executor.submit(() -> {
    throw new IllegalArgumentException("bad input");
});

CompletableFuture<String> f2 =
        CompletableFuture.failedFuture(
                new IllegalStateException("service unavailable"));
~~~

This snippet requires declaring `executor`. Although the Future types differ, calling `get()` on a failed computation follows the `Future` contract.

The difference lies in the additional APIs: `CompletableFuture` provides `join`, `handle`, `exceptionally`, `whenComplete`, `thenCompose`, and many ways to compose stages without requiring the caller to wait immediately at each step.

## 4. CompletionException: the contract of CompletableFuture.join()

`CompletableFuture.join()` waits for the result like `get()` in that it can **block**, but it **does not declare checked exceptions**. If the stage completed exceptionally from a computation, `join()` typically throws `CompletionException` wrapping the cause.

~~~java
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IllegalStateException("remote API failed"));

try {
    failed.join();
} catch (CompletionException ex) {
    System.out.println(ex.getCause().getMessage());
}
~~~

Stdout of this **snippet** when run inside a valid method:

~~~text
remote API failed
~~~

`join()` has no overload accepting a timeout. If you need to bound waiting time on the caller, you can use `get(timeout, unit)`; meanwhile `CompletableFuture.orTimeout` alters the **completion state of the future** if it does not finish in time and does not automatically interrupt the background computation.

### 4.1. Why can CompletionException also appear in the middle of a chain?

With `CompletableFuture`, an exception can arise from a callback of `thenApply`, `thenCombine`, `thenCompose`, `supplyAsync`, or another stage.

~~~java
CompletableFuture<Integer> parsed =
        CompletableFuture.completedFuture("not-a-number")
                .thenApply(Integer::parseInt);
~~~

The `parsed` stage completes exceptionally because of `NumberFormatException`; when the caller invokes `parsed.join()`, it observes `CompletionException` with a cause related to `NumberFormatException`.

**Callbacks receiving `Throwable` do not always receive the same wrapper shape** at every position in a chain. Depending on the stage, you may receive the root cause directly or a `CompletionException` wrapping it. Error-handling code should therefore inspect the cause chain instead of hard-coding `(MyDomainException) error.getCause()` without type and `null` checks.

### 4.2. CompletableFuture.get() vs. join() on the same future

This is a systematic difference:

| Observation | `CompletableFuture.get()` | `CompletableFuture.join()` |
| --- | --- | --- |
| Does it wait if not yet done? | Yes | Yes |
| When completed successfully | Returns result | Returns result |
| When completed exceptionally | Typically throws `ExecutionException` | Typically throws `CompletionException` |
| Computation error exception type | Checked | Unchecked |
| When cancelled | `CancellationException` | `CancellationException` |
| If caller is interrupted while waiting | May throw `InterruptedException` | Does not declare `InterruptedException` |
| Direct timeout | `get(timeout, unit)` | No `join(timeout)` |
| Need to get the cause? | `ex.getCause()` | `ex.getCause()` |

The `CompletableFuture` Javadoc also notes: if the exceptional completion carries a `CompletionException`, the `get` overloads may throw `ExecutionException` with the **same cause** inside that wrapper, whereas `join` may throw that `CompletionException` itself. **Do not assume the two APIs produce cause chains with the same number of layers**, even when the underlying failure is identical.

## 5. Safely extracting the root cause

### 5.1. Unwrap known wrappers, do not strip layers arbitrarily

A helper that is usually sufficient for the two wrappers covered here:

~~~java
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

static Throwable unwrapAsyncFailure(Throwable error) {
    Throwable current = error;

    // Bound depth to avoid anomalous cycles in the cause chain.
    for (int depth = 0; depth < 32; depth++) {
        boolean asyncWrapper =
                current instanceof ExecutionException
                || current instanceof CompletionException;

        if (!asyncWrapper) {
            break;
        }

        Throwable cause = current.getCause();
        if (cause == null || cause == current) {
            break;
        }
        current = cause;
    }
    return current;
}
~~~

This is a valid **Java method snippet** when placed inside a class, not a standalone program. The function unwraps only **`ExecutionException` and `CompletionException`**. If it encounters `IllegalStateException`, `SQLException`, a domain error, or a wrapper with different semantics, it **stops** so the application can decide.

Why not just write `while (t.getCause() != null) t = t.getCause()`?

- A domain layer like `PaymentRejectedException` may hold a technical cause, yet it is itself the signal that needs to be mapped into a business error.
- `DataAccessException`, `UndeclaredThrowableException`, reflection wrappers, and HTTP client exceptions have their own contracts.
- Logging only the bottom-most error loses the fact that the failure crossed an asynchronous boundary and mapping layers.
- An anomalous cause chain can make an unbounded loop unsafe; limiting depth and checking self-cause are defensive measures.

**Do not strip the wrapper from logs.** You can use the unwrapped cause to **classify** the error, while still logging the full `Throwable` at the observation boundary:

~~~java
try {
    return future.get(5, TimeUnit.SECONDS);
} catch (ExecutionException ex) {
    Throwable cause = unwrapAsyncFailure(ex);
    logFailure("Async execution failed", ex, cause);
    throw translateToDomainError(cause);
}
~~~

This is an illustrative snippet; you must implement `logFailure`, `translateToDomainError`, `future`, and catch the other exceptions from `get(timeout)`. Avoid repeatedly logging full stack traces across multiple layers, which creates noise; each boundary should have clear responsibility.

### 5.2. Cause, suppressed exceptions, and stack trace

These three pieces of data are not synonymous:

- **Cause (`getCause()`)**: the `Throwable` attached as the direct cause of a wrapper or higher-level error.
- **Suppressed (`getSuppressed()`)**: additional errors, such as failures closing resources in `try-with-resources`; **not** part of the cause chain.
- **Stack trace**: call stacks where each `Throwable` was created/thrown; with async, the wrapper and the cause may record **two different threads/boundaries**.

Do not replace the full exception with `logger.error("{}", ex.getMessage())`, because the message usually lacks type, cause, and stack trace. Avoid logging sensitive data in inputs, URLs with tokens, request bodies, or internal details that should be masked.

## 6. Standalone Java 17 example: comparing get, join, cause, and recovery

This example **does not require Spring** to verify standard JDK semantics. It uses `CompletableFuture.failedFuture(...)` with a deterministic error and `ExecutorService.submit(...)` to show both Future sources are wrapped when using `get`.

Create the exact file **`FutureExceptionDemo.java`**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class FutureExceptionDemo {

    public static void main(String[] args) throws Exception {
        IllegalStateException root =
                new IllegalStateException("database unreachable");

        CompletableFuture<String> failed =
                CompletableFuture.failedFuture(root);

        try {
            failed.get();
        } catch (ExecutionException ex) {
            printFailure("get", ex);
        }

        try {
            failed.join();
        } catch (CompletionException ex) {
            printFailure("join", ex);
        }

        Throwable nested = new CompletionException(
                new ExecutionException(root));
        System.out.println("nested root: " +
                unwrap(nested).getMessage());

        String fallback = failed.exceptionally(ex -> "cached").join();
        System.out.println("exceptionally: " + fallback);

        String handled = failed.handle((value, error) ->
                error == null ? value : "recovered").join();
        System.out.println("handle: " + handled);

        CompletableFuture<String> observed =
                failed.whenComplete((value, error) -> {
                    // Observe only; does not replace the original error.
                });
        System.out.println("whenComplete stays failed: " +
                observed.isCompletedExceptionally());

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> submitted = pool.submit(() -> {
                throw new IllegalArgumentException("bad request");
            });

            try {
                submitted.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException ex) {
                printFailure("submit", ex);
            }
        } finally {
            pool.shutdown();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    private static void printFailure(String label, Throwable error) {
        Throwable root = unwrap(error);
        System.out.println(label + " wrapper: " +
                error.getClass().getSimpleName());
        System.out.println(label + " root: " +
                root.getClass().getSimpleName() +
                ": " + root.getMessage());
    }

    private static Throwable unwrap(Throwable error) {
        Throwable current = error;
        for (int depth = 0; depth < 32; depth++) {
            if (!(current instanceof ExecutionException)
                    && !(current instanceof CompletionException)) {
                break;
            }

            Throwable cause = current.getCause();
            if (cause == null || cause == current) {
                break;
            }
            current = cause;
        }
        return current;
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac FutureExceptionDemo.java
java FutureExceptionDemo
~~~

**Exact stdout** under normal execution conditions:

~~~text
get wrapper: ExecutionException
get root: IllegalStateException: database unreachable
join wrapper: CompletionException
join root: IllegalStateException: database unreachable
nested root: database unreachable
exceptionally: cached
handle: recovered
whenComplete stays failed: true
submit wrapper: ExecutionException
submit root: IllegalArgumentException: bad request
~~~

**Explanation of each observation:**

1. `failedFuture(root)` creates a `CompletableFuture` already completed exceptionally with `IllegalStateException`.
2. `get()` throws **`ExecutionException`**; `join()` throws **`CompletionException`**. Different wrappers, yet the helper finds the root error for both.
3. `new CompletionException(new ExecutionException(root))` simulates two wrapping layers; the helper strips exactly two layers.
4. `exceptionally(...)` produces a **recovery** stage with the value `cached`.
5. `handle(...)` is called for both success and failure outcomes; here it returns `recovered`.
6. `whenComplete(...)` only observes; when the callback does not throw, the returned stage remains **exceptional** because the upstream stage failed.
7. `ExecutorService.submit` accepts a `Callable` that throws `IllegalArgumentException`. `Future.get` reports `ExecutionException`, whose cause is the error from the `Callable`. Using `get(timeout)` here ensures the test does not hang indefinitely if the environment behaves abnormally.
8. `finally` shuts down the pool created by the example so no threads outlive the program.

The output is constructed from deterministic exception types/messages and completed Futures, rather than relying on thread ordering or random timing. The program could still be affected if the JVM lacks resources to create a worker or is abnormally interrupted; the stdout above is the contract for the normal path.

## 7. In Spring @Async: how do execution errors travel through the proxy?

In Spring, `@Async` in default proxy mode requires:

1. `@EnableAsync` active in the right `ApplicationContext`.
2. The service/worker is a **Spring-managed bean**.
3. The method call goes through the **Spring proxy**; self-invocation `this.method()` usually does not trigger the annotation.
4. An appropriate executor is selected, for instance via `@Async("ioExecutor")`.
5. The method returns a valid type: `void`, `Future<T>`, or `CompletableFuture<T>` depending on the API/version.

Example method inside a service bean:

~~~java
@Async("ioExecutor")
public CompletableFuture<String> fetch(String key) {
    if (key.isBlank()) {
        throw new IllegalArgumentException("blank key");
    }
    return CompletableFuture.completedFuture(loadFromRemote(key));
}
~~~

This is an **illustrative method snippet** requiring imports for `@Async`, `CompletableFuture`, `loadFromRemote`, and the `ioExecutor` bean. If `loadFromRemote` throws an exception on the worker, the Future returned to the caller can complete exceptionally. `get()` on that Future typically reports `ExecutionException`; `join()` reports `CompletionException`.

**Do not confuse errors from the Spring proxy with the root error.** The wrapper still follows JDK Future/CompletionStage semantics; the business exception of the `fetch` method lies in the cause chain.

### 7.1. @Async void: no Future for the caller

~~~java
@Async("ioExecutor")
public void refreshIndex() {
    throw new IllegalStateException("index write failed");
}
~~~

This is an illustrative snippet. When a method returns `void`, the caller **has no Future on which to call `get` or `join`**, so exceptions running on the worker do not automatically surface on the caller. Spring provides `AsyncUncaughtExceptionHandler` to handle these kinds of errors. Example configuration inside a `@Configuration` class:

~~~java
@EnableAsync
@Configuration
class AsyncErrorConfiguration implements AsyncConfigurer {
    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {
        return (error, method, args) ->
                System.err.println("Async void error in " +
                        method.getName() + ": " + error);
    }
}
~~~

This is a **configuration snippet**, requiring imports for `AsyncConfigurer`, `AsyncUncaughtExceptionHandler`, `@EnableAsync`, `@Configuration`, and a production logging policy. If the application has multiple configuration classes, organize them so you do not accidentally declare multiple conflicting `AsyncConfigurer` beans.

For tasks where the caller needs to know **whether it succeeded or failed**, consider `CompletableFuture<T>` and/or durable job status. `@Async void` cannot propagate exceptions directly back to the caller simply via a `try/catch` around the call.

### 7.2. Rejection and errors before the worker runs

A saturated pool may **refuse to accept** the task. When the handler throws an exception, the submitting side may see `RejectedExecutionException` or `TaskRejectedException` at **submission time**, instead of `ExecutionException` when retrieving the result. If `DiscardPolicy` or `DiscardOldestPolicy` silently drops work, the Future may never complete; **there is no wrapper** to unwrap.

Therefore, investigating “`@Async` failed” requires identifying whether the error happened during **submission**, **execution**, **completion-stage callback**, or **waiting**. All four points can report errors differently.

## 8. Spring Framework demo: get and join on the same @Async method

This standalone demo uses **Java 17+, Spring Framework 6.1.14, and Gradle 8.5+**. It needs no Spring Boot, servlet container, or database. The worker bean `FailureWorker` intentionally throws an `IllegalStateException` on the Spring executor; the caller reads it with `get(timeout)`, `join()`, and creates a recovery branch.

### 8.1. File structure

~~~text
spring-async-exception-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/AsyncRootCauseDemo.java
~~~

**settings.gradle**:

~~~groovy
rootProject.name = 'spring-async-exception-demo'
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
}

application {
    mainClass = 'demo.AsyncRootCauseDemo'
}
~~~

**src/main/java/demo/AsyncRootCauseDemo.java**:

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class AsyncRootCauseDemo {

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            FailureWorker worker = context.getBean(FailureWorker.class);

            // Submit both jobs first; the caller observes the errors later.
            CompletableFuture<String> a = worker.load("A");
            CompletableFuture<String> b = worker.load("B");

            try {
                a.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException ex) {
                printFailure("get", ex);
            }

            try {
                b.join();
            } catch (CompletionException ex) {
                printFailure("join", ex);
            }

            CompletableFuture<String> recovered =
                    worker.load("C")
                            .exceptionally(error -> "cached-C");
            System.out.println("fallback: " +
                    recovered.get(5, TimeUnit.SECONDS));
        }
    }

    private static void printFailure(String label, Throwable error) {
        Throwable cause = error;
        for (int depth = 0; depth < 32; depth++) {
            if (!(cause instanceof ExecutionException)
                    && !(cause instanceof CompletionException)) {
                break;
            }
            if (cause.getCause() == null ||
                    cause.getCause() == cause) {
                break;
            }
            cause = cause.getCause();
        }

        System.out.println(label + " wrapper: " +
                error.getClass().getSimpleName());
        System.out.println(label + " root: " +
                cause.getClass().getSimpleName() +
                ": " + cause.getMessage());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {
        @Bean("ioExecutor")
        public ThreadPoolTaskExecutor ioExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("io-");
            return executor;
        }

        @Bean
        public FailureWorker failureWorker() {
            return new FailureWorker();
        }
    }

    public static class FailureWorker {
        @Async("ioExecutor")
        public CompletableFuture<String> load(String key) {
            throw new IllegalStateException("load failed: " + key);
        }
    }
}
~~~

In the project directory, run:

~~~bash
gradle run
~~~

If Gradle Wrapper is present, use `./gradlew run` on Linux/macOS or `gradlew.bat run` on Windows.

**Lines printed by the program itself** when the executor starts and the Futures complete within the wait timeout:

~~~text
get wrapper: ExecutionException
get root: IllegalStateException: load failed: A
join wrapper: CompletionException
join root: IllegalStateException: load failed: B
fallback: cached-C
~~~

Spring or Gradle may print startup logs outside the five lines above. Thread names/latency vary at runtime, but the code does not print worker names so expected stdout does not depend on scheduling.

**Explanation:** `@EnableAsync` enables async infrastructure; `FailureWorker` is created by Spring via `@Bean` and the proxy can intercept the public `load` method. The caller obtains the worker from the context instead of instantiating it with `new` outside. When the method throws `IllegalStateException` on the executor thread, the Future returned from the proxy captures the error; `get` and `join` expose different wrappers. `exceptionally` handles the exceptional state to supply a fallback value. That is a **caller-level decision**, not Spring automatically fixing the root error.

## 9. Handling errors in CompletableFuture chains

### 9.1. exceptionally: recovers only on the failure branch

~~~java
CompletableFuture<String> safe =
        worker.load("A").exceptionally(error -> {
            Throwable root = unwrapAsyncFailure(error);
            recordFailure(root);
            return "cached-value";
        });
~~~

This snippet requires `unwrapAsyncFailure`, `recordFailure`, and the `worker` bean. If upstream succeeds, the `exceptionally` callback is not invoked; if it fails, the callback chooses a fallback. Choosing a fallback **does not mean the original data was processed successfully** — you must clearly define semantics and job status.

### 9.2. handle: handles both success and failure

~~~java
CompletableFuture<Result> result = worker.load("A")
        .handle((value, error) -> {
            if (error != null) {
                return Result.failed(unwrapAsyncFailure(error));
            }
            return Result.success(value);
        });
~~~

This snippet requires defining the `Result` type and helper. `handle` runs after the previous stage completes, letting you convert **both success and failure** into an application-domain result type. However, if the `handle` callback throws an exception itself, the new stage can still complete exceptionally.

### 9.3. whenComplete: observes without turning failure into success

~~~java
CompletableFuture<String> traced = worker.load("A")
        .whenComplete((value, error) -> {
            if (error != null) {
                logFailure(unwrapAsyncFailure(error));
            }
        });
~~~

The snippet above does not recover from errors on its own. When the original stage failed, the `traced` stage still completes exceptionally if the callback only logs. Do not use `whenComplete` as if it were equivalent to `exceptionally`.

### 9.4. thenApply/thenCompose: errors propagate through dependencies

~~~java
CompletableFuture<String> output = worker.load("A")
        .thenApply(String::trim)
        .thenApply(String::toUpperCase);
~~~

If `load("A")` fails, normal transformation callbacks **do not run**; the `output` future can also end exceptionally. Individual callbacks do not each need their own `try/catch` if you already have a suitable shared error-handling boundary.

With `thenCompose`, the callback returns another Future; if the previous stage fails, the callback is typically not called and the error passes downstream. Errors from the Future returned by the callback also become errors of the composed stage. This can add another `CompletionException` layer when the caller calls `join`.

### 9.5. allOf and multiple simultaneous failures

~~~java
CompletableFuture<Void> all =
        CompletableFuture.allOf(taskA, taskB, taskC);
~~~

This is a snippet; the Futures must already be created. When one or more branches complete exceptionally, `all` can complete exceptionally; **do not treat a single cause as the full list of errors across all three branches**. If business logic requires per-task error reporting, inspect each Future carefully after completion, or convert each branch into a `Result` holding success/failure before aggregating.

Do not call `CompletableFuture.allOf(...).join()` right in the middle of an execution flow without knowing how the branches were submitted and handled. If an async API across layers is needed, return the combined future instead of blocking the caller.

## 10. Timeout, cancellation, and interruption are not ExecutionException

A solid error-handling boundary must distinguish:

| Signal | Where does it typically come from? | Appropriate action |
| --- | --- | --- |
| `ExecutionException` | `Future.get()` after a computation failed | Inspect cause; map/retry/log based on cause |
| `CompletionException` | `CompletableFuture.join()` or stage exception | Inspect cause; do not treat the wrapper as a domain error |
| `TimeoutException` | `get(timeout)` or timeout source | Distinguish **waiting** timeout from a failed/stopped task |
| `InterruptedException` | Caller interrupted while waiting in `get` | Respect cancellation/shutdown, usually restore interrupt flag |
| `CancellationException` | Future was cancelled | Handle cancelled state; do not treat as a normal computation error |
| `RejectedExecutionException`/`TaskRejectedException` | Executor rejected at submission | Backpressure, overload response, bounded retries, or durable queue |

### 10.1. Handling get(timeout) intentionally

~~~java
try {
    return future.get(5, TimeUnit.SECONDS);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new OperationCancelledException(ex);
} catch (TimeoutException ex) {
    throw new DownstreamTimeoutException(ex);
} catch (CancellationException ex) {
    throw new OperationCancelledException(ex);
} catch (ExecutionException ex) {
    Throwable failure = unwrapAsyncFailure(ex);
    throw mapToApplicationException(failure);
}
~~~

This is an **illustrative code snippet**; `future`, the application-domain exceptions, and the mapping function are not defined. The catch order above merely illustrates policy. When catching `InterruptedException`, restoring the interrupt flag is usually appropriate if the exception is not propagated as-is by contract, giving the thread lifecycle a chance to react properly.

**Timing out while waiting does not automatically cancel the work.** Even `future.cancel(true)` only requests/attempts cancellation per contract/implementation; it cannot guarantee every I/O operation or external side effect stops immediately. With `CompletableFuture`, cancellation is a form of exceptional completion and does not automatically control all source tasks submitted elsewhere.

### 10.2. Using orTimeout/completeOnTimeout while understanding the consequences

~~~java
CompletableFuture<String> timed =
        worker.load("A").orTimeout(3, TimeUnit.SECONDS);
~~~

`orTimeout` can complete the `CompletableFuture` **exceptionally** if it does not finish in time; `completeOnTimeout` can complete it with a default value. These APIs do not guarantee that a running computation is interrupted or that database operations automatically roll back. If the `timed` stage fails due to timeout, `get` and `join` can still expose it through wrappers containing `TimeoutException`.

If timeouts are used for both the HTTP request and the worker, clearly specify which status represents caller timeout, which represents downstream timeout, and which represents the final job outcome. Do not use the exception message as a sole status code.

## 11. Mapping root causes to business behavior

Once the cause category is identified, the service/controller layer can decide:

~~~text
Async wrapper
    |
    v
Unwrap ExecutionException / CompletionException
    |
    +-- Validation/domain exception ---> return input error or domain state
    |
    +-- Timeout/temporary network -----> bounded retry or 503/504
    |
    +-- Cancellation ------------------> cancelled state, do not retry indiscriminately
    |
    +-- Data integrity/permanent ------> report stable error, do not retry blindly
    |
    +-- Unknown -----------------------> log fully, return safe error response
~~~

This is an example of **design-level handling rules**, not a mandatory HTTP mapping table for every API. The protocol layer must separate internal exceptions from information permitted to be returned to clients. Never send stack traces, SQL, access tokens, or confidential details in HTTP responses.

**Do not retry every `ExecutionException`.** The wrapper does not indicate whether the error is transient. Retrying requires checking the **root cause**, operation **idempotency**, retry budget, exponential backoff/jitter, and load limits. A business error such as invalid parameters will not resolve itself if retried identically. A task that already caused side effects before failing may create duplicates if retried without an idempotency key.

Similarly, do not swallow everything with `exceptionally(e -> null)` if `null` causes upper layers to assume success. A fallback must have clear semantics (such as a valid cached read) or be converted into a `Result.failed(...)` type.

## 12. Error observability: logging, tracing, and consistency

An error crossing an async boundary can carry:

- **Worker thread**: where `IllegalStateException`, `SQLException`, etc. originated.
- **Caller thread**: where `get`/`join` is called and sees the wrapper.
- **Trace/correlation ID**: connects both activities belonging to one request/job.
- **Job ID**: identifies the specific task and timestamps for submission, start, completion, or failure.
- **Executor metadata**: pool name, queue size, rejection count, active threads, and latency.

**Log fully once at the responsible boundary**, for example passing the whole `Throwable` to the logger instead of only the message. Depending on your observability strategy, you can add the **unwrapped cause type** as a classification field while preserving the full cause chain for investigation.

Illustrative pseudocode:

~~~java
Throwable cause = unwrapAsyncFailure(error);
logger.error("async_job_failed jobId={} causeType={}",
        jobId, cause.getClass().getSimpleName(), error);
~~~

`logger`, `jobId`, and the helper must be defined. With SLF4J, a trailing `Throwable` argument is typically interpreted by the logger as a stack trace; exact log formatting depends on binding/version. Do not log sensitive data or raw inputs unnecessarily.

**MDC and ThreadLocal do not propagate automatically across `@Async`** because the worker runs on a different thread. If trace/correlation IDs are needed on the worker, explicitly pass them in a DTO or configure appropriate context propagation/`TaskDecorator`, and clean up afterward to prevent data leakage between tasks sharing the thread pool.

### 12.1. Measure state before deciding the cause

Do not guess “the Future hung because of an exception”: the task might still be waiting in the queue, running slowly, deadlocked, or silently rejected/dropped by a handler. An incomplete Future **has no `ExecutionException` to unwrap**. Check pool saturation, submitted/started/completed/rejected counters, task age, timeouts, and thread dumps when appropriate.

If `@Async` does not actually execute through the Spring proxy (for example self-invocation or an object created via `new`), the error may be thrown **synchronously right on the caller**. Never assume every exception from an annotated method passes through `CompletableFuture`.

## 13. Common anti-patterns and how to fix them

| Anti-pattern | Problem | Correct approach |
| --- | --- | --- |
| Logging only `ex.getMessage()` of `ExecutionException` | Loses cause and stack trace | Log full `Throwable`, inspect `getCause()` when classifying |
| `catch (Exception e) { return null; }` | Hides errors, caller assumes success | Return valid fallback or failed stage, log/map clearly |
| `(IOException) ex.getCause()` without type checking | `ClassCastException` or wrong wrapper assumption | Unwrap known wrappers, check `instanceof` before mapping |
| Assuming `join()` is non-blocking | Can still block the thread | Use continuations, join only at boundaries needing the result |
| Retrying every `CompletionException` | Ignores cause, may duplicate side effects | Retry based on cause + idempotency + budget |
| Expecting `@Async void` to throw back to caller | Caller has no result Future | Use Future if monitoring is needed, or `AsyncUncaughtExceptionHandler` |
| Treating `TimeoutException` from `get` as a worker error | Timeout is only a **waiting** limit | Track task state and cancel/retry per contract |
| Swallowing `InterruptedException` and continuing | Breaks cancellation/shutdown semantics | Restore interrupt flag or propagate appropriately |
| Treating `allOf`'s cause as all errors | May miss other failed branches | Aggregate results/errors per branch |
| Dropping Future without attaching an observer | Background errors go unhandled | Keep handle, callback, metrics/job status |
| Using `DiscardPolicy` for critical tasks | Tasks vanish silently, Future may stay pending | Explicit rejection, backpressure, or durable queue |
| Calling `future.get()` on a single-thread worker pool when child needs same pool | Can cause starvation deadlock | Use continuations or separate dependencies/pools |

## 14. Testing and code review checklist

### 14.1. Minimum tests

1. **Success**: `get`/`join` returns the expected value.
2. **Worker failure**: `get` catches `ExecutionException`, cause holds the expected exception.
3. **Failure via CompletableFuture**: `join` throws `CompletionException`, cause is unwrapped properly.
4. **Multiple wrappers**: `CompletionException(new ExecutionException(root))` is stripped properly by the helper without losing domain errors.
5. **Fallback**: `exceptionally`/`handle` returns values per contract, `whenComplete` does not replace failure on its own.
6. **One failing branch in allOf**: downstream handles exceptional completion, checks per-branch status when needed.
7. **Cancellation**: verify `CancellationException` rather than `ExecutionException`.
8. **Wait timeout**: `get(timeout)` throws `TimeoutException` and does not stop the task by default.
9. **Interruption**: an interrupted caller handles the flag and lifecycle properly.
10. **Spring context**: `@EnableAsync`, worker bean, qualifier, and proxy work; verify errors through Future from another bean.
11. **@Async void**: handler records the error, without relying on caller catch.
12. **Overloaded pool**: task rejection is observed; do not confuse rejection with computation failure.

### 14.2. Pre-production review

- [ ] Distinguish `ExecutionException` and `CompletionException` according to `get`/`join` APIs.
- [ ] Do not unwrap every `Throwable` layer indiscriminately; keep full exception chains in logs.
- [ ] Separately catch `InterruptedException`, `TimeoutException`, `CancellationException`, and rejections as needed.
- [ ] `@Async` is invoked through a bean/proxy of the right `ApplicationContext`.
- [ ] Select executors via qualifiers when multiple pools exist.
- [ ] Do not call `get()`/`join()` prematurely when the goal is overlapping independent tasks.
- [ ] Have an error-handling boundary: fallback, mapping, retry, or meaningful error result.
- [ ] Have appropriate timeouts and cancellation/cleanup policies.
- [ ] Have metrics for root exception types, queue saturation, rejections, and long-running job states.
- [ ] For mandatory tasks, ensure durability via job store/outbox/broker instead of only in-memory Futures.

## 15. Self-check questions

1. **Does `Future.get()` throwing `ExecutionException` prove the executor broke?** No. It is usually a wrapper around an error thrown in the computation; inspect `getCause()`.
2. **Is `CompletableFuture.join()` non-blocking because it throws an unchecked exception?** No. It can still block waiting for the result.
3. **For the same `CompletableFuture.failedFuture(root)`, what do `get` and `join` typically throw?** `get` throws `ExecutionException`; `join` throws `CompletionException`, both linked to `root`.
4. **If `get(timeout)` times out, has the worker failed?** Not necessarily. That is a timeout while the caller waited; the task may still be running.
5. **Does a cancelled Future throw `ExecutionException`?** Typically it throws `CancellationException`.
6. **Does calling `ex.getCause()` once always yield the root error?** No. There may be multiple wrappers or a meaningful domain layer.
7. **Why shouldn't you unwrap `getCause()` all the way to the bottom?** It can lose application-layer exception semantics and error propagation context.
8. **How does `exceptionally` differ from `whenComplete`?** `exceptionally` can recover with a value; `whenComplete` mainly observes and does not turn failure into success.
9. **Does `handle` run on both success and failure?** Yes; the callback receives the corresponding value/error.
10. **Does a failed `CompletableFuture.allOf` report every error from every task?** No; to report all of them, inspect each branch individually.
11. **With `@Async void`, can the caller retrieve errors via `Future.get`?** There is no Future to call; you need a handler/logging/other monitoring.
12. **If an `@Async` method is self-invoked with `this.method()`, does the exception pass through the Future proxy?** Usually not, because self-invocation bypasses the proxy in default mode.
13. **Why log both the wrapper and the cause?** To capture both the async boundary and the technical/business root cause.
14. **Does a `CompletionException` mean you should immediately retry?** No. Retry decisions depend on the cause, idempotency, and retry budget.

**Remember:** `ExecutionException` and `CompletionException` are typically **wrappers for asynchronous errors**, not root causes. Knowing how `get()` and `join()` report errors, unwrapping safely, preserving full stack traces, and distinguishing timeout/cancellation/rejection enables proper business handling in Java and Spring `@Async`.

### Official references

- [Java 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java 17 — ExecutionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html)
- [Java 17 — CompletionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — @Async](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Spring Framework — AsyncUncaughtExceptionHandler](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/aop/interceptor/AsyncUncaughtExceptionHandler.html)
