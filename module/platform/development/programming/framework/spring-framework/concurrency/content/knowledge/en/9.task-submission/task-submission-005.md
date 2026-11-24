# Exception Propagation Differences Between execute() and submit()

> **Topic:** Spring Framework – Concurrency / Task Submission and Retrieval.  
> **Key Takeaway:** With an executor running on worker threads, `execute(Runnable)` can let uncaught exceptions escape `Runnable.run()` and flow through the worker's exception handling mechanism. Meanwhile, common `ExecutorService.submit(...)` implementations wrap work in a `FutureTask`, retain the exception in the `Future`, and let callers retrieve it via `Future.get()` as an `ExecutionException`. However, both can throw **submission failures** directly on the caller; and a synchronous executor or `CallerRunsPolicy` can alter the exception propagation path.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **in-task** exceptions from **submission-time** exceptions.
2. State the contracts of `Executor.execute(Runnable)`, `ExecutorService.submit(Runnable)`, `submit(Callable<T>)`, and the role of `Future`.
3. Explain `FutureTask`, `ExecutionException.getCause()`, `UncaughtExceptionHandler`, and `ThreadPoolExecutor.afterExecute`.
4. Predict when a caller's `try/catch` catches an exception and when it does not.
5. Analyze edge cases in Spring `ThreadPoolTaskExecutor`, `TaskDecorator`, `@Async void`, and `@Async Future/CompletableFuture`.
6. Write runnable Java 17 examples, read stdout reliably, and design consistent error handling, timeouts, cancellation, and rejection handling.

## 2. First: Two Very Different Points of Failure

An executor call typically involves two phases:

~~~text
Caller
   |
   +-- execute(task) / submit(task)
   |      |
   |      +-- Phase 1: accept or reject task
   |                |
   |                +-- rejection -> exception directly on caller
   |
   +-- Phase 2: run task (worker, or sometimes caller)
          |
          +-- Runnable/Callable code succeeds
          |
          +-- Runnable/Callable code throws exception
                 |
                 +-- Raw Runnable: may become worker uncaught exception
                 |
                 +-- FutureTask: stores exception, read via Future.get()
~~~

**Submission failure:** the executor cannot accept more work due to shutdown, saturation, invalid arguments, or an error detected during dispatch. JDK's `RejectedExecutionException`, or `TaskRejectedException` through Spring's abstraction, may be thrown directly at the call site. A `catch` wrapping `execute/submit` has the opportunity to catch this kind of error.

**Task failure:** the work was accepted, and later code inside `run()/call()` throws an error (e.g., `IllegalStateException`, network error, data error). For tasks running on a worker, this is a **different call stack**. It does not automatically jump back to a catch block the caller has already exited.

Keep these two failure types separate in every design for logging, API responses, retries, and status tracking. `submit` returns a `Future` only when the submission method itself returns normally; not every rejection error gets "turned into a failed Future".

## 3. execute(Runnable): No Default Result Channel

The `java.util.concurrent.Executor` interface is tiny:

~~~java
public interface Executor {
    void execute(Runnable command);
}
~~~

The method returns `void`, so the call itself **has no `Future`** to wait on, cancel, or read results from. With a standard `ThreadPoolExecutor` when the task is a raw `Runnable`:

- The caller may return after the pool accepts the task.
- A worker invokes `Runnable.run()`.
- If `run()` throws an uncaught `RuntimeException`/`Error`, the task terminates abnormally. The `afterExecute(...)` hook may receive the exception; the worker's `Thread.UncaughtExceptionHandler` may also handle it.
- Because the error occurs on the worker, a typical caller `catch` **cannot catch it**; some environments print stack traces to stderr, which is not a business error-reporting guarantee for the caller.
- The worker thread may terminate and be replaced by the pool; do not equate "one task died from an error" with "the whole pool is broken".

An easily misunderstood code example:

~~~java
try {
    pool.execute(() -> {
        throw new IllegalStateException("inside worker");
    });
} catch (IllegalStateException ex) {
    // Will not automatically catch the worker's error here.
}
~~~

This is a **snippet**: `pool` must be a declared and initialized variable.

**Exception to the rule:** An `Executor` may run `command.run()` directly on the caller (such as a direct executor / Spring's `SyncTaskExecutor`). In addition, when a pool is saturated, `CallerRunsPolicy` can run the task directly on the caller. In those cases, a raw `Runnable` error can throw directly through `execute`. You cannot make an absolute statement that "`execute` never throws task errors to the caller".

## 4. submit(...): FutureTask Changes the Exception Path

`ExecutorService` adds the `submit` API:

~~~java
Future<?> submit(Runnable task);
<T> Future<T> submit(Callable<T> task);
<T> Future<T> submit(Runnable task, T result);
~~~

With common implementations based on `AbstractExecutorService`:

1. `submit` creates a `FutureTask`-like wrapper to track status.
2. The executor is asked to run the wrapper (typically via the underlying `execute(...)` mechanism).
3. When the task throws an exception, `FutureTask.run()` **catches and stores** the exception in the Future's failed state; the exception does not escape the wrapper's `run()` like a raw `Runnable`.
4. `Future.get()` on the caller waits until a result is ready. If the task failed, `get()` throws `ExecutionException`, and `getCause()` holds the original exception.
5. If `Runnable` succeeds and you called `submit(Runnable)` without specifying a result, `get()` returns `null`; if using `Callable<T>`, `get()` returns the `T` computed by the task.

~~~text
Caller                                 Worker
  |                                      |
  +-- submit(task)                       |
  |     +-- FutureTask(task) ------------+-- FutureTask.run()
  |     +-- return Future                 |    +-- invokes task
  |                                      |    +-- task throws
  |                                      |    +-- FutureTask keeps cause
  |                                      |
  +-- future.get() ----------------------+-- Future completes
          |
          +-- ExecutionException
                |
                +-- getCause() -> actual error from task
~~~

Saying "`submit` swallows exceptions" is inaccurate. **The error remains inside the Future**, but when an application forgets the `Future` and has no other observer, the error can become **operationally invisible**.

## 5. Comparison Table of Error Reception Paths

| Criterion | `execute(Runnable)` | `submit(Runnable/Callable)` |
| --- | --- | --- |
| Root interface | `Executor` | `ExecutorService`; in Spring, executors supporting `submit` |
| Return value | `void` | `Future<?>` or `Future<T>` |
| Task outcome | No handle returned by the method | `Future.get()`: `T`, preset result, or `null` |
| Task exception on typical worker pool | Usually escapes `Runnable.run()` → hook/uncaught handler | Usually captured by the `FutureTask` wrapper |
| How caller learns the task failed | Proactively design callbacks/error channels | Call `Future.get()` / use completion observers |
| Caller exception at submission time | May throw rejection | Can also throw rejection before a Future exists |
| Caller catches task logic exception directly? | Possible if task runs on caller; usually not if on worker | Usually must read error from Future, even if `CallerRunsPolicy` runs wrapper on caller |
| Task cancellation | Method returns no cancellation handle | `Future.cancel(...)` provides best-effort cancellation |
| Guarantees task runs on a different thread? | No | Also no |

The two columns describe common implementations, not every custom executor. Pay attention to **the actual object type executed by the executor**: a `FutureTask` passed to `execute` also captures exceptions from the underlying logic!

## 6. Standalone Java 17: Seeing Both Exception Paths Clearly

This runnable example uses a single worker and a `ThreadFactory` setting a custom `UncaughtExceptionHandler`, avoiding reliance on default stderr stack traces. `CountDownLatch` preserves output order, and `Future.get(timeout)` prevents reading results early.

Create **`ExecuteSubmitExceptionDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.FutureTask;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ExecuteSubmitExceptionDemo {

    public static void main(String[] args) throws Exception {
        CountDownLatch handlerDone = new CountDownLatch(1);
        AtomicInteger uncaughtEvents = new AtomicInteger();

        ThreadFactory factory = work -> {
            Thread thread = new Thread(work, "demo-worker");
            thread.setUncaughtExceptionHandler((t, ex) -> {
                uncaughtEvents.incrementAndGet();
                System.out.println("uncaught = "
                        + ex.getClass().getSimpleName()
                        + ": " + ex.getMessage());
                handlerDone.countDown();
            });
            return thread;
        };

        ExecutorService pool =
                Executors.newSingleThreadExecutor(factory);
        try {
            pool.execute(() -> {
                throw new IllegalStateException("execute-fail");
            });

            if (!handlerDone.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("handler timed out");
            }
            System.out.println("execute has Future = false");

            Future<?> failed = pool.submit(() -> {
                throw new IllegalArgumentException("submit-fail");
            });

            try {
                failed.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException ex) {
                Throwable cause = ex.getCause();
                System.out.println("submit cause = "
                        + cause.getClass().getSimpleName()
                        + ": " + cause.getMessage());
            }

            Future<String> success = pool.submit(() -> "OK");
            System.out.println("callable result = "
                    + success.get(5, TimeUnit.SECONDS));

            Future<?> done = pool.submit(() -> { });
            System.out.println("runnable result = "
                    + done.get(5, TimeUnit.SECONDS));

            // Use execute, yet pass in a FutureTask.
            FutureTask<Integer> wrapped = new FutureTask<>(() -> {
                throw new IllegalArgumentException("wrapped-fail");
            });
            pool.execute(wrapped);
            try {
                wrapped.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException ex) {
                System.out.println("wrapped cause = "
                        + ex.getCause().getMessage());
            }
            System.out.println("uncaught events = "
                    + uncaughtEvents.get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac ExecuteSubmitExceptionDemo.java
java ExecuteSubmitExceptionDemo
~~~

**Expected exact stdout on a successful run:**

~~~text
uncaught = IllegalStateException: execute-fail
execute has Future = false
submit cause = IllegalArgumentException: submit-fail
callable result = OK
runnable result = null
wrapped cause = wrapped-fail
uncaught events = 1
~~~

Explanation:

- The first error escapes the raw `Runnable.run()` dispatched by `execute`; the custom worker handler prints `uncaught` and increments the counter.
- `handlerDone.await()` prevents main from printing the next line before the handler executes.
- The error from `submit` is retrieved via `Future.get()` before printing, without incrementing uncaught events.
- Successful `submit(Callable<String>)` returns `OK`. Successful `submit(Runnable)` returns `null`.
- A `FutureTask` submitted via **`execute`** itself still captures the exception: proving the wrapper matters more than the method name.
- `newSingleThreadExecutor` can replace the failed worker, and subsequent tasks still process normally. `shutdown/awaitTermination` cleans up resources.

This is a **standalone runnable program**, requiring neither Maven nor Spring. It does not use `Thread.sleep` to create lucky execution timing.

## 7. An Important Trap: execute(FutureTask) Is Not Like execute(raw Runnable)

The following code:

~~~java
FutureTask<Integer> wrapped = new FutureTask<>(() -> {
    throw new IllegalStateException("boom");
});
pool.execute(wrapped);
wrapped.get();
~~~

is an **illustrative snippet**, requiring `pool`, importing `FutureTask`, and handling checked exceptions.

If `wrapped` is a `FutureTask`, the original error is caught inside `FutureTask.run()`, **not** terminating the worker abnormally the way a raw `Runnable` does. `wrapped.get()` throws `ExecutionException` wrapping `IllegalStateException`.

This illuminates a deeper point: typical `submit` implementations also call the execution layer with a wrapper holding result state. **The same executor and the same error can travel two different observation channels simply because one side wraps the work in a FutureTask**. Hence, when debugging, do not just read `execute/submit` at the call site; know what object actually sits in the queue.

## 8. Why Does a Caller-Side try/catch Usually Not Work?

~~~java
try {
    executor.execute(() -> {
        throw new IllegalStateException("worker failed");
    });
} catch (IllegalStateException ex) {
    // Will not automatically enter here if the task runs on another worker.
}
~~~

This is not a standalone runnable class because `executor` is uninitialized.

`try/catch` executes on the caller's call stack. A task on a worker has the worker's call stack, so exceptions cannot "jump threads" into the caller's catch block without an explicit signal/result-passing mechanism.

However, a catch on the caller **can** catch an error when:

1. A synchronous executor invokes `Runnable.run()` directly on the caller, such as `SyncTaskExecutor`.
2. A pool saturates with `CallerRunsPolicy` and the handler calls `run()` on a raw `Runnable` directly on the caller.
3. Submission/decorator-evaluation code throws synchronously before the task is dispatched.
4. The executor rejects the task with an exception because it is shut down or full.

Therefore, both "`execute` always propagates task errors to the caller" and "`execute` never propagates errors to the caller" **are false** without specifying the implementation and where the task runs.

## 9. Submission Failures: Both execute and submit Can Throw Immediately

With a shut-down `ExecutorService`:

~~~java
ExecutorService executor = Executors.newSingleThreadExecutor();
executor.shutdown();

try {
    executor.submit(() -> System.out.println("never runs"));
} catch (java.util.concurrent.RejectedExecutionException ex) {
    System.out.println("submission rejected on caller");
}
~~~

This snippet can be placed in a method importing `ExecutorService`/`Executors`. In common JDK implementations using `AbortPolicy`, the exception occurs **at the `submit` call**, not as a task error stored inside a Future. When `submit` throws this way, it does not return a successful Future for the caller to read.

### 9.1. Rejection Policy Can Change the Error Path

| `ThreadPoolExecutor` policy | Raw `execute(Runnable)` when full | `submit(...)` (FutureTask wrapper) when full |
| --- | --- | --- |
| `AbortPolicy` | Throws `RejectedExecutionException` on caller | Throws rejection on caller, returns no Future |
| `CallerRunsPolicy`, not shut down | Caller runs `Runnable.run()`; error may throw directly | Caller runs FutureTask; task exception is usually stored for `get()` |
| `DiscardPolicy` | Task may be dropped without caller knowing | May receive a Future that **never completes**, if wrapper is dropped |
| `DiscardOldestPolicy` | Drops head task from queue to try enqueuing new task | Future of evicted task may never complete without extra cancellation |

Do not choose silent discard policies for business operations requiring success/failure confirmation unless separate cancellation, compensation, or observation exists. With `CallerRunsPolicy`, an HTTP request may unexpectedly run the task on the request thread, increasing latency. With `submit`, the `FutureTask` still holds the error even when execution happens on the caller.

### 9.2. TaskRejectedException in Spring

Spring's `ThreadPoolTaskExecutor` implements the `TaskExecutor` abstraction and typically translates underlying executor rejections into `org.springframework.core.task.TaskRejectedException`:

~~~java
import org.springframework.core.task.TaskRejectedException;

try {
    reportExecutor.execute(job);
} catch (TaskRejectedException ex) {
    // Enforce overload policy: fail fast, bounded retry,
    // return appropriate error, or hand off to a durable job store.
}
~~~

This is a **snippet**, requiring `reportExecutor`/`job` to be declared. `TaskRejectedException` is a **submission-time failure**, not an `ExecutionException` inside `Future.get()`. When using `submit`, code must handle **both immediate rejection at call time** and **execution failure read from the Future later**.

## 10. Future.get: Reading Errors, Results, Timeouts, and Cancellation Properly

### 10.1. ExecutionException and the Root Cause

`Future.get()` can wait until the task completes. If the task fails, `get()` throws an `ExecutionException` and `getCause()` returns the original logic exception. For example:

~~~text
Future.get()
   |
   +-- ExecutionException
           |
           +-- getCause()
                   |
                   +-- IllegalArgumentException("bad input")
~~~

A snippet using a timeout:

~~~java
try {
    String answer = future.get(3, TimeUnit.SECONDS);
    return answer;
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    throw new IllegalStateException("task failed", cause);
} catch (TimeoutException ex) {
    future.cancel(true);
    throw new IllegalStateException("task timed out", ex);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    future.cancel(true);
    throw new IllegalStateException("wait interrupted", ex);
} catch (CancellationException ex) {
    throw new IllegalStateException("task cancelled", ex);
}
~~~

This is a **method-body snippet**, requiring `Future<String> future` and imports for the corresponding exceptions. It illustrates one policy, not a rule that you must always cancel on timeout.

Important:

- `get(timeout)` throwing `TimeoutException` means **the caller stopped waiting**; the task may still be running.
- `cancel(true)` only **attempts** cancellation, typically via interrupt; if the task is doing blocking I/O that ignores interrupts, it may keep running.
- When catching `InterruptedException`, usually restore the interrupt flag or propagate an appropriate exception.
- `CancellationException` differs from business exceptions and from rejection errors.
- `Future.isDone() == true` can mean success, failure, or cancellation. You cannot look solely at isDone to conclude the task succeeded.

### 10.2. Successful Runnable Has get() == null

~~~java
Future<?> f = executor.submit(() -> doSideEffect());
Object value = f.get(); // null when Runnable completes normally.
~~~

This is a snippet with `executor` and `doSideEffect()` declared by the application. `null` is the normal completion value of the `submit(Runnable)` overload, not an error indicator.

### 10.3. Do Not Abandon the Future

~~~java
executor.submit(() -> {
    sendMessage();
    throw new IllegalStateException("message failed");
});

// Neither storing Future, nor calling get, nor callback, nor job-status.
~~~

The snippet above can leave the error stored inside `FutureTask` with nobody reading it. If business logic must not block the caller, use callbacks/completion observers or persisted job status. If work must continue after restarts/crashes, use a durable message queue/job store, not only an in-memory thread pool.

## 11. afterExecute() and UncaughtExceptionHandler: Why the Two Failures Look Different

`ThreadPoolExecutor` provides a hook:

~~~java
protected void afterExecute(Runnable task, Throwable error);
~~~

For a raw `Runnable` throwing an uncaught exception, `error` may be that exception. However, with `submit(...)`, `FutureTask.run()` catches and records the exception in the Future's state, so `afterExecute(..., error)` **typically receives `error == null`** even though the task logic failed.

The Java SE Javadoc suggests inspecting the Future wrapper once complete:

~~~java
@Override
protected void afterExecute(Runnable task, Throwable error) {
    super.afterExecute(task, error);

    if (error == null
            && task instanceof Future<?> future
            && future.isDone()) {
        try {
            future.get();
        } catch (CancellationException ex) {
            error = ex;
        } catch (ExecutionException ex) {
            error = ex.getCause();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
    }

    if (error != null) {
        reportFailure(error);
    }
}
~~~

This is a **method inside a `ThreadPoolExecutor` subclass**, not standalone; it requires imports for Future and the exceptions, plus an application-defined `reportFailure(...)` method.

Because `future.isDone()` is true, calling `get()` in this pattern does not wait for an incomplete task. Distinguish intentional cancellation from business failure; custom wrappers/decorators can cause `task` to no longer be directly an instance of `Future`, so do not treat this snippet as a universal solution.

**Thread.UncaughtExceptionHandler** can observe exceptions that terminate a worker abnormally, yet is normally not invoked for task failures retained by a `FutureTask`. And even if the handler logs the error, the caller still **does not automatically receive a business outcome**. Build a separate feedback path if needed.

## 12. Spring ThreadPoolTaskExecutor: Using the Right Error Channel

Spring Framework provides `ThreadPoolTaskExecutor`, supporting `execute` and `submit`. A bean configuration may look like:

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class ExecutorConfig {
    @Bean("businessExecutor")
    ThreadPoolTaskExecutor businessExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(32);
        pool.setThreadNamePrefix("business-");
        pool.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return pool; // Container initializes and destroys the pool.
    }
}
~~~

This is a **Spring configuration snippet**, not a standalone program; it requires an application with `spring-context` or the corresponding Spring Boot starter.

- `execute` is used to submit a `Runnable`; if a raw task runs on a worker and throws, it may go to the worker's uncaught/error observer without automatically returning to the caller.
- `submit` returns a `Future` allowing the caller to read the cause via `get()`.
- When the queue/pool is full, the rejection policy determines whether an error occurs at submission time, runs on the caller, or drops the task.
- A `TaskDecorator` can wrap the executed object; with `submit`, that object is usually already a `FutureTask`.

### 12.1. Service Using submit and Retaining the Future

~~~java
import java.util.concurrent.Future;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final ThreadPoolTaskExecutor executor;

    public ReportService(
            @Qualifier("businessExecutor")
            ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    public Future<String> start(String jobId) {
        return executor.submit(() -> runJob(jobId));
    }

    private String runJob(String jobId) {
        if (jobId == null || jobId.isBlank()) {
            throw new IllegalArgumentException("missing jobId");
        }
        return "done:" + jobId;
    }
}
~~~

This is a **service snippet** for a Spring application; there is no `main`. The key point is not merely "calling submit", but that the caller must **own the Future**, inspect completion/failure, and translate that outcome into proper business state.

### 12.2. Standalone Spring Context Example Running with Maven + Java 17

This small project demonstrates `ThreadPoolTaskExecutor.submit(Callable)` retaining exceptions and Spring managing lifecycle; no Spring Boot or Web server is needed.

Structure:

~~~text
spring-exception-demo/
├── pom.xml
└── src/main/java/demo/SpringFutureDemo.java
~~~

File **`pom.xml`**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-exception-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.16</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File **`src/main/java/demo/SpringFutureDemo.java`**:

~~~java
package demo;

import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class SpringFutureDemo {

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean("workExecutor")
        ThreadPoolTaskExecutor workExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(8);
            pool.setThreadNamePrefix("work-");
            pool.setRejectedExecutionHandler(
                    new ThreadPoolExecutor.AbortPolicy());
            return pool;
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            ThreadPoolTaskExecutor executor =
                    context.getBean("workExecutor",
                            ThreadPoolTaskExecutor.class);

            Future<String> failed = executor.submit(() -> {
                throw new IllegalStateException("spring-failed");
            });

            try {
                failed.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException ex) {
                Throwable cause = ex.getCause();
                System.out.println("spring cause = "
                        + cause.getClass().getSimpleName()
                        + ": " + cause.getMessage());
            }

            Future<Integer> good = executor.submit(() -> 40 + 2);
            System.out.println("spring result = "
                    + good.get(5, TimeUnit.SECONDS));
        }
    }
}
~~~

Run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SpringFutureDemo
~~~

**Demo class stdout** on a successful run (excluding separate Maven notices if any):

~~~text
spring cause = IllegalStateException: spring-failed
spring result = 42
~~~

`get(5, TimeUnit.SECONDS)` waits for the Future to finish; the original exception is retrieved from `ExecutionException`. The context manages the bean and shuts down the executor when closing the context. This is the Spring error path corresponding to `submit`; the Java 17 example in section 6 clearly demonstrated the `execute` error path.

## 13. Spring's TaskDecorator Has a Trap with submit

`ThreadPoolTaskExecutor#setTaskDecorator(...)` allows wrapping the executed callback to set MDC/tracing, measure duration, or log:

~~~java
executor.setTaskDecorator(original -> () -> {
    try {
        original.run();
    } catch (RuntimeException ex) {
        logger.error("task failed", ex);
        throw ex;
    }
});
~~~

This is a **snippet**, assuming `executor` and `logger` exist. With a raw `execute(Runnable)`, the decorator can see exceptions escaping `run()`. However, on the `submit` path, `original` is usually a `FutureTask` or a callback wrapping it. `FutureTask.run()` keeps the error inside, so the catch in the decorator **may not execute** even when the underlying task failed.

Spring's Javadoc includes an official note about this case. If you need to observe all failures, do not rely solely on `TaskDecorator.catch`. Ensure there is a `Future` owner / completion observer, or build an error-monitoring layer that understands the wrapper and avoids blocking workers.

## 14. @Async void and @Async Future/CompletableFuture

`@Async` is Spring's interception abstraction; exceptions thrown by an `@Async`-annotated method follow a path depending on **return type**. `@EnableAsync` (or equivalent config) must be enabled and invocations must go **through the proxy**; self-invocation via `this.method()` in default proxy mode does not trigger async interception.

### 14.1. @Async void: No Future for the Caller

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
class MailService {
    @Async("businessExecutor")
    public void send(String recipient) {
        throw new IllegalStateException("mail failed");
    }
}
~~~

This is a service snippet. The caller has no `Future` to receive errors. For `@Async void` with valid interception, Spring uses `AsyncUncaughtExceptionHandler` to handle exceptions thrown by the method. The default handler typically logs the error; applications can register a custom handler.

This is **not** Java's `Thread.UncaughtExceptionHandler`. Do not assume every `@Async void` error will kill the worker or automatically appear in a controller's try/catch.

### 14.2. Customizing AsyncUncaughtExceptionHandler

~~~java
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration(proxyBeanMethods = false)
@EnableAsync
class AsyncErrorConfig implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (error, method, args) -> {
            System.err.println("async method failure = "
                    + method.getName() + ": " + error.getMessage());
            // Real app: log with correlation ID, alert, update job-status.
        };
    }
}
~~~

This is a **Spring configuration class**, without `main`. With `@Async("businessExecutor")`, Spring selects the executor specified by bean name/qualifier. This configuration handles **exceptions from void @Async methods**; it does not replace the caller reading the `Future` when a method returns a Future.

### 14.3. @Async Returning CompletableFuture

~~~java
@Async("businessExecutor")
public CompletableFuture<String> load(String key) {
    if (key.isBlank()) {
        throw new IllegalArgumentException("empty key");
    }
    return CompletableFuture.completedFuture("value:" + key);
}
~~~

This is a method snippet requiring imports for `CompletableFuture` and `@Async`. If invoked through the Spring proxy:

- The caller receives a `CompletableFuture` to track completion.
- `future.get()` fails with `ExecutionException` wrapping the cause.
- `future.join()` typically throws `CompletionException` (unchecked) wrapping the cause on failure.
- `whenComplete`, `handle`, or `exceptionally` allow non-blocking handling.
- Direct calls on the same instance bypassing the proxy follow the normal Java call stack and are not forced to run asynchronously.

An observer:

~~~java
service.load(key).whenComplete((value, error) -> {
    if (error != null) {
        logger.error("load failed for key={}", key, error);
    }
});
~~~

This is integration code requiring `service`, `key`, and `logger`. The callback may run on the thread that completes the future, so do not attach caller `ThreadLocal`/transaction assumptions to it. An exception inside the callback can fail the callback's completion stage; monitor that error path too when it matters.

## 15. CompletableFuture Also Proves the Wrapper Matters

~~~java
CompletableFuture<Integer> f = CompletableFuture.supplyAsync(
        () -> {
            throw new IllegalStateException("calculation failed");
        },
        executor);

f.whenComplete((value, ex) -> {
    if (ex != null) {
        report(ex);
    }
});
~~~

This is a snippet assuming `executor` implements `Executor` and a `report` method exists.

Even if the implementation uses `Executor.execute(...)` to dispatch internal callbacks, `CompletableFuture` has its own mechanism to record completion/exception state. Therefore, the rule "execute always goes to the uncaught handler" is wrong whenever the executed object has an error-capturing wrapper.

Differences to remember:

| Result-reading API | On typical failure |
| --- | --- |
| `Future.get()` | `ExecutionException` (checked), `getCause()` holds original cause |
| `CompletableFuture.get()` | `ExecutionException` (checked) |
| `CompletableFuture.join()` | `CompletionException` (unchecked), inspect cause to classify |
| `whenComplete(...)` | Receives both value and error upon completion without blocking caller |
| `exceptionally(...)` | Can replace failure with a fallback value |
| `handle(...)` | Transforms both success and failure, can change the final result |

Future/completion does not guarantee running on a different thread; if the executor is a direct executor, execution can happen directly on the caller.

## 16. Designing Error Handling by Responsibility

| Scenario | Suitable observation channel | Points to watch |
| --- | --- | --- |
| `execute` with raw Runnable on worker | Worker error handler / structured task logging | Caller gets no automatic outcome; report failures with job ID |
| `submit` with failing Callable | `Future.get()`, completion observer | Do not abandon Future; unwrap `ExecutionException` |
| `@Async void` failure | `AsyncUncaughtExceptionHandler` | No Future returned to caller |
| `@Async CompletableFuture` failure | Future exceptional / callback | Do not block HTTP requests indefinitely |
| Pool rejects at submission | `RejectedExecutionException` / Spring `TaskRejectedException` | Decide fail fast, backpressure, retry, or durable queue |
| Task cancelled | `CancellationException` | Intentional cancellation is not necessarily a business failure |
| Future wait exceeds deadline | `TimeoutException` | Task may continue running after timeout |
| Waiting thread interrupted | `InterruptedException` | Restore interrupt or propagate per policy |
| FutureTask in `afterExecute` | Inspect `Future.get()` if done | `Throwable == null` does not prove task succeeded |

A practical rule is **one owner for outcome state**. If the worker, decorator, callback, controller, and service all log the same exception, duplicate logs appear and root cause analysis becomes harder. Define clearly where job status is updated, where logs are emitted, and where client errors are returned.

### 16.1. Wrapper That Logs Errors While Preserving Failure State

~~~java
public static Runnable withErrorReport(
        String jobId,
        Runnable work,
        java.util.function.BiConsumer<String, Throwable> reporter) {
    return () -> {
        try {
            work.run();
        } catch (RuntimeException | Error ex) {
            reporter.accept(jobId, ex);
            throw ex;
        }
    };
}
~~~

This is a **method suitable for a utility class**. It reports errors right where the task runs, even if the task is later submitted via `submit` and wrapped into a FutureTask. Avoid letting `reporter` throw and mask the original cause; in production, build robust observers, aim for single-point logging, and update status cleanly.

### 16.2. Task Errors, Transactions, and Context

`@Transactional` normally binds transaction association to a thread. If a task runs on a worker, the caller's transaction does not follow automatically, whether using `execute` or `submit`. Similarly, MDC/tracing, security context, or request context typically require explicit propagation solutions. **An error not delivered to the caller** also does not mean the caller's transaction will automatically roll back when the worker throws.

If business logic needs errors to drive transactions or HTTP responses, design explicit synchronization/orchestration points and proper transaction boundaries rather than just adding a try/catch outside the submission call.

## 17. Testing Exception Paths Properly

### 17.1. Testing submit with Future.get

JUnit 5 example, **snippet** requiring pool fixture, imports, and assertions:

~~~java
Future<?> failed = pool.submit(() -> {
    throw new IllegalArgumentException("invalid");
});

ExecutionException ex = assertThrows(
        ExecutionException.class,
        () -> failed.get(3, TimeUnit.SECONDS));

assertEquals(IllegalArgumentException.class,
        ex.getCause().getClass());
assertEquals("invalid", ex.getCause().getMessage());
~~~

Do not use `Thread.sleep(100)` and look for stack traces in logs. With `submit`, errors can be stored in the Future without printing to stderr.

### 17.2. Testing execute with a Synchronized Handler

Provide a custom `ThreadFactory` that puts `Throwable` into a `BlockingQueue<Throwable>` or decrements a `CountDownLatch` after seeing the exception. The test waits with a bounded timeout and asserts the exception type. The Java 17 example in section 6 does exactly this, avoiding dependence on scheduler timing.

### 17.3. Edge Cases That Must Be Tested

- Runtime errors inside `execute(Runnable)` on a worker.
- Runtime errors inside `submit(Runnable/Callable)`, including exact cause after `Future.get()`.
- `execute(FutureTask)` to verify the wrapper captures errors.
- Rejection errors when the executor is shut down or full.
- `CallerRunsPolicy` with raw Runnable and FutureTask wrapper.
- `Future.get(timeout)`, cancellation, and interruption; tasks may keep running if unresponsive to interrupts.
- Spring `TaskDecorator` with `submit`, `@Async void` with handler, and `@Async CompletableFuture`.
- Non-duplicated error logging with job ID/correlation ID and without leaking sensitive data.
- Clean teardown of executors and Spring contexts after tests.

## 18. Common Misconceptions

**1. "`execute` always throws task exceptions to the caller."** False: workers have a separate call stack. The caller only sees synchronous or submission errors without a dedicated result mechanism.

**2. "`execute` never throws errors."** False: synchronous executors, `CallerRunsPolicy`, and rejections can still throw to the caller.

**3. "`submit` swallows errors forever."** False: the Future holds the cause; `get()` or an observer is required. Errors are only lost when the app ignores the result.

**4. "`submit` returning a Future means the task has finished."** False: the Future may be pending, queued, failed, or cancelled.

**5. "A `try/catch` around `submit` catches `IllegalStateException` from the worker."** No, if the failure happened inside an accepted task; inspect `ExecutionException.getCause()`.

**6. "`afterExecute(..., null)` means success."** False for `FutureTask`, which can retain errors without throwing out of `run()`.

**7. "`TaskDecorator` `catch(Exception)` catches all `submit` errors."** False when the `FutureTask` wrapper has already captured the exception.

**8. "`Future.isDone()` means success."** False: isDone is true for normal, exceptional, and cancelled completions alike.

**9. "If `get(timeout)` times out, the task is cancelled."** False: timing out only ends the wait unless cancellation or a deadline mechanism is explicitly invoked.

**10. "`@Async void` will throw errors back to the controller."** False on the proxied async path; Spring invokes `AsyncUncaughtExceptionHandler`.

**11. "`Future.get` and `CompletableFuture.join` are identical."** False regarding checked vs. unchecked exception classes.

**12. "Switching `execute` to `submit` is enough to monitor all failures."** False unless Futures are retained/inspected and submission rejections are handled.

**13. "`CallerRunsPolicy` only affects performance, not exceptions."** False: with a raw Runnable, the task can throw directly on the caller; with FutureTask, errors are still stored.

**14. "Every exception should be retried."** False: classify invalid inputs, transient failures, rejections, and cancellations; retries require backoff/idempotency to avoid amplifying overload.

## 19. Self-Check Questions

**Question 1:** `pool.submit(() -> { throw new IllegalStateException("x"); })` returns a Future. When does the caller learn of the error?

**Answer:** when calling `future.get()` (or an equivalent observer); with standard JDK implementations, `get` throws `ExecutionException` whose cause is `IllegalStateException`.

**Question 2:** Does `pool.execute(new FutureTask<>(callable))` guarantee going through `UncaughtExceptionHandler` if `callable` fails?

**Answer:** no. `FutureTask` stores the exception and may exit `run()` normally; you still need to read `FutureTask.get()`.

**Question 3:** The pool shuts down before `submit`, and the caller catches `RejectedExecutionException`. Is this an error inside the task's logic?

**Answer:** no, this is a submission failure. The task was not accepted, so no valid Future is returned.

**Question 4:** The pool is full with `CallerRunsPolicy`. Why might `execute` of a raw Runnable throw immediately, while `submit` of equivalent logic returns a failed Future?

**Answer:** `CallerRunsPolicy` runs `Runnable.run()` directly on the caller; however, on the `submit` path, the Runnable being executed is the `FutureTask` wrapper that captures the exception.

**Question 5:** An `@Async public void send()` method fails. Can the caller invoke `get()`?

**Answer:** no, because the method returns `void`. You need `AsyncUncaughtExceptionHandler` or to change the API design to `Future/CompletableFuture` if the caller needs the outcome.

**Question 6:** Why does `Future.isDone() == true` not mean the task succeeded?

**Answer:** the done state covers success, failure, and cancellation; `get()` or a completion mechanism is required to classify it.

## 20. Pre-Implementation Checklist

- [ ] Know the executor implementation, where tasks run, and whether caller-runs/synchronous execution is possible.
- [ ] Separate task execution exceptions from immediate submission-time exceptions.
- [ ] With `execute`, have a failure observation mechanism and task ID tracking if needed by business logic.
- [ ] With `submit`, establish clear `Future` ownership and where `get()`/observation occurs.
- [ ] Never rely solely on `afterExecute`'s `Throwable` or `TaskDecorator.catch` to conclude a submitted task had no error.
- [ ] Catch `ExecutionException` and preserve the root cause; distinguish timeout, cancellation, and interruption.
- [ ] Do not let `get()` wait indefinitely when the caller has a deadline.
- [ ] Handle pool rejections explicitly; do not retry infinitely on request threads.
- [ ] For `@Async void`, configure an exception handler; for Future/CompletableFuture, ensure a consumer/observer exists.
- [ ] Have a safe logging/tracing policy without duplicate log entries.
- [ ] Have durable job storage if tasks must not be lost on crash/restart.
- [ ] Test execution errors, submission errors, cancellation, shutdown, and load saturation.

## 21. Summary

**`execute(Runnable)`** returns `void`. With raw tasks running on a `ThreadPoolExecutor` worker, uncaught exceptions can reach worker error/uncaught handling rather than automatically returning to the caller. However, synchronous executors, `CallerRunsPolicy`, or submission rejections can still surface exceptions directly on the caller.

**`submit(...)`** returns a `Future`. In common implementations, the task is wrapped by `FutureTask`; task errors are captured and delivered to the caller when `get()` throws `ExecutionException` holding the original cause. **Abandoning a Future without an observer** is a monitoring design flaw.

In Spring, `ThreadPoolTaskExecutor` shares these semantics, plus the `TaskDecorator` caveat and the two distinct error paths of `@Async void` versus `@Async CompletableFuture`. Design explicit result channels, error-handling ownership, deadlines, cancellation, and rejection policies rather than guessing from method names.

## Official References

- Java SE 17 — `Executor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html
- Java SE 17 — `ExecutorService` (submit, lifecycle): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 17 — `Future` (get, cancel, isDone): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- Java SE 17 — `FutureTask`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html
- Java SE 17 — `ThreadPoolExecutor` (afterExecute, rejection): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Spring Reference — Task Execution and Scheduling, `@Async` Exception Management: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Javadoc — `ThreadPoolTaskExecutor`: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Javadoc — `AsyncUncaughtExceptionHandler`: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/aop/interceptor/AsyncUncaughtExceptionHandler.html
