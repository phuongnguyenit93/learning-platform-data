# Do Not Discard a Future and Lose Business Errors

## 1. The problem: the task fails, yet the system does not know

A Spring API receives an invoice-generation request, dispatches a task to an executor, and receives a `Future` or `CompletableFuture`. Then the code discards the returned handle:

~~~java
// Anti-pattern: snippet inside a service, not a standalone class.
invoiceWorker.generateInvoice(invoiceId); // CompletableFuture<Invoice>
return "Accepted";
~~~

If the worker throws `IllegalStateException` due to an invalid invoice, the error **may be stored inside the Future** instead of propagating to the HTTP thread. Without calling `get()/join()`, attaching a completion handler, persisting job status, or having another monitoring mechanism, the business layer may forever think the job succeeded. Even when the Future has `isDone() == true`, that state **does not mean success**.

Common consequences:

- Clients receive an “already processed” response yet no invoice exists; no corresponding business error code is surfaced.
- `ExecutorService.submit` catches `Callable` exceptions inside `FutureTask`, so **no stack trace may appear from the thread's uncaught-exception handler**.
- `CompletableFuture.supplyAsync` completes exceptionally without forcing the application to observe it; `thenApply` chains run only on success, while failed stages are skipped.
- `@Async` returning `Future/CompletableFuture` allows propagating errors to the caller via the result, yet **the caller must consume or forward the handle**.
- Failures in critical jobs turn into “silent failures”, impacting money, inventory, email, audit trails, and consistency.

**Rule:** whenever code **submits work and receives a Future**, it must specify **who owns the Future, who observes its terminal state, who records business errors, and who notifies or retries**. You do not necessarily have to block with `get()`; you can attach `whenComplete`, return the Future to the caller, or persist job status in a durable store.

## 2. What is a Future really?

### 2.1. execute, submit, CompletableFuture, and @Async

| API | What does the caller receive? | How are in-task errors handled? |
| --- | --- | --- |
| `Executor.execute(Runnable)` | `void` | Unchecked exceptions can escape `run()` and be handled by the executor/thread uncaught handler; depends on implementation |
| `ExecutorService.submit(Callable<T>)` | `Future<T>` | Exception is stored in the Future; `get()` throws `ExecutionException` with `getCause()` |
| `CompletableFuture.supplyAsync(supplier, executor)` | `CompletableFuture<T>` | Stage completes exceptionally; `join()` typically throws `CompletionException`, `get()` throws `ExecutionException` |
| `@Async` returning `CompletableFuture<T>` | Returned proxy Future | Method exceptions can be observed via the Future; must pass along or attach a handler |
| `@Async` returning `void` | No Future | Uses `AsyncUncaughtExceptionHandler`/logging/metrics since the caller receives no exception via a Future |
| Executor rejects task at submission | May **not return a Future** | `RejectedExecutionException` (JDK) or `TaskRejectedException` (Spring), depending on adapter/policy |

`Future` and `CompletableFuture` represent a **later** result, not proof that the task succeeded. When a task is rejected, cancelled, dropped from a queue, or stuck in I/O, the handling path also differs. Design must account for both **submission failure** and **execution failure**, not just catching exceptions in the business method.

### 2.2. A completed Future is not necessarily successful

| State | `Future.isDone()` | `get()` | Needs handling? |
| --- | --- | --- | --- |
| Queued/running | `false` | May wait | Deadlines, timeouts, queue health |
| Succeeded | `true` | Returns result | Update `SUCCEEDED` |
| Threw business error | `true` | `ExecutionException` | Record `FAILED`, classify error, retry when appropriate |
| Cancelled | `true` | `CancellationException` | Record `CANCELLED` |
| Silently discarded before running | May remain `false` forever | May wait forever | Explicit rejection, time bounds, reconciliation |

`CompletableFuture.isCompletedExceptionally()` returns `true` when the result completed exceptionally, including cases such as cancellation. `Future.isDone()` does not tell you the reason, and simply calling `isDone()` does not cause errors to be logged automatically.

## 3. Why can submit() hide errors?

Java's `ExecutorService.submit(Callable<T>)` typically wraps the task in a `RunnableFuture/FutureTask`. `FutureTask` catches exceptions from `Callable.call()` and stores them in the Future's state. A worker thread can move on to the next task without printing the previous task's exception directly to stderr. If the caller merely drops or ignores the `Future` reference, the business error sits there unhandled.

~~~java
// Snippet; assumes executor is a running ExecutorService.
Future<String> result = executor.submit(() -> {
    throw new IllegalArgumentException("invalid invoice");
});

// Do not discard result if the business operation requires completion.
// Normal return from submit() does not mean the task succeeded.
~~~

Bounded synchronous observation:

~~~java
// Snippet at a boundary needing the result (not a standalone program).
try {
    String path = result.get(3, TimeUnit.SECONDS);
    markSucceeded(path);
} catch (ExecutionException ex) {
    Throwable businessCause = ex.getCause();
    markFailed(businessCause);
} catch (TimeoutException ex) {
    markTimedOut(ex);
    // Decide further cancellation/retry per business contract.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    markInterrupted(ex);
} catch (CancellationException ex) {
    markCancelled(ex);
}
~~~

`markSucceeded`/`markFailed`/`markTimedOut`/`markInterrupted`/`markCancelled` are hypothetical application operations. Requires `import java.util.concurrent.*;`. `get(timeout)` only bounds **how long the caller waits**; it does not automatically cancel the task or move an incomplete Future into a terminal state.

An HTTP controller that needs to respond quickly **should not** call `get()` right after submitting and call that background processing. Instead, return an appropriate asynchronous API response or return `202 Accepted` with a job ID **after genuinely accepting/persisting the request**, then provide a status-lookup endpoint.

## 4. Java 17: standalone example demonstrating errors held inside a Future

The complete example below does not depend on race conditions or thread scheduling to verify results: a **single-worker** executor runs the failing task, then runs a marker task. `marker.get(...)` guarantees the failing task has finished before inspection. The `CompletableFuture` section uses `failedFuture` and `whenComplete` to demonstrate observation and *accidental error swallowing*.

Save with exact name **`FutureFailureDemo.java`**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class FutureFailureDemo {
    static final class BusinessException extends RuntimeException {
        BusinessException(String message) {
            super(message);
        }
    }

    static Throwable unwrap(Throwable error) {
        while ((error instanceof ExecutionException
                || error instanceof CompletionException)
                && error.getCause() != null) {
            error = error.getCause();
        }
        return error;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            // Worker captures BusinessException inside FutureTask.
            Future<String> failedSubmit = executor.submit(() -> {
                throw new BusinessException("invalid invoice");
            });

            // Single-threaded worker processes marker after failedSubmit.
            Future<String> marker = executor.submit(() -> "marker");
            System.out.println("MARKER=" + marker.get(3, TimeUnit.SECONDS));
            System.out.println("SUBMIT_DONE=" + failedSubmit.isDone());

            try {
                failedSubmit.get(3, TimeUnit.SECONDS);
            } catch (ExecutionException ex) {
                System.out.println("SUBMIT_CAUSE="
                        + unwrap(ex).getClass().getSimpleName());
            }

            CompletableFuture<String> failed =
                    CompletableFuture.failedFuture(
                            new BusinessException("stock mismatch"));

            AtomicInteger observedCount = new AtomicInteger();
            CompletableFuture<String> observed =
                    failed.whenComplete((value, error) -> {
                        if (error != null) {
                            observedCount.incrementAndGet();
                        }
                    });

            try {
                observed.join();
            } catch (CompletionException ex) {
                System.out.println("OBSERVED_CAUSE="
                        + unwrap(ex).getClass().getSimpleName());
            }
            System.out.println("OBSERVATIONS=" + observedCount.get());

            // Fallback makes the NEW stage succeed; original error remains.
            CompletableFuture<String> fallback =
                    failed.exceptionally(ex -> "DEFAULT");
            System.out.println("FALLBACK=" + fallback.join());

            String handled = failed.handle((value, error) ->
                    error == null ? value
                            : "FAILED:" + unwrap(error).getMessage()).join();
            System.out.println("HANDLED=" + handled);
            System.out.println("ORIGINAL_EXCEPTIONAL="
                    + failed.isCompletedExceptionally());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(3, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac --release 17 FutureFailureDemo.java
java FutureFailureDemo
~~~

Stdout **printed by the program**, in exact order:

~~~text
MARKER=marker
SUBMIT_DONE=true
SUBMIT_CAUSE=BusinessException
OBSERVED_CAUSE=BusinessException
OBSERVATIONS=1
FALLBACK=DEFAULT
HANDLED=FAILED:stock mismatch
ORIGINAL_EXCEPTIONAL=true
~~~

**Explanation:** the failing task has finished once `marker` finishes on the same single-threaded executor. `SUBMIT_DONE=true` does not signify success; only when calling `failedSubmit.get` is the `BusinessException` cause revealed. With `CompletableFuture.failedFuture`, `whenComplete` increments the counter without **fixing the error**; `observed.join()` still throws `CompletionException`. Conversely, `exceptionally` turns the error into the fallback string `DEFAULT` in a **new stage**. Because the original `failed` stays exceptional, `ORIGINAL_EXCEPTIONAL=true`.

The example uses deterministic values, makes no network calls, needs no Spring, uses no `Thread.sleep`, and does not rely on random ordering across multiple workers. It only explains semantics; in production, replace `System.out` with loggers/metrics and update job status.

## 5. CompletableFuture tools: choose rightly so errors are not lost

### 5.1. whenComplete: observe and forward state

~~~java
// Snippet; future has type CompletableFuture<Invoice>.
CompletableFuture<Invoice> observed =
        future.whenComplete((invoice, error) -> {
            if (error != null) {
                log.error("invoice failed, invoiceId={}", invoiceId, error);
            }
        });
return observed;
~~~

`log`/`invoiceId` and `Invoice` belong to the application service. `whenComplete` runs on both success and failure, making it suitable for structured logging, metrics, or lightweight auditing. **It returns a new Future carrying the same status/result by default**, without turning errors into success. If the callback itself throws while upstream succeeded, the returned stage can fail too; if upstream had already failed, the upstream cause takes precedence per the `CompletionStage` contract.

**Do not attach a callback and abandon every other monitoring path** when logging can also fail. For critical operations, still maintain DB job status / outbox, retries, and reconciliation. Moreover, `whenComplete` does not create its own worker: the callback can run on the thread completing the stage or on the caller when already done. Keep callbacks short and avoid long I/O/blocking on completion threads.

### 5.2. handle: transform both success and failure into a new value

~~~java
// Snippet inside a service; Outcome type is application-defined.
record Outcome<T>(String status, T value, String errorCode) { }

CompletableFuture<Outcome<Invoice>> outcome = future.handle(
        (value, error) -> error == null
                ? new Outcome<>("SUCCEEDED", value, null)
                : new Outcome<>("FAILED", null, mapErrorCode(error)));
~~~

`mapErrorCode` is a business method; this snippet is not standalone. Because `handle` returns a new value, the `outcome` stage can **complete normally even when upstream failed**. This is valid when the API contract is to return a result with explicit status. However, if you simply `return null` or return a default “success” object on error, you are **hiding business errors**.

### 5.3. exceptionally: intentional recovery, without swallowing every error

~~~java
// Snippet: allow fallback only when the auxiliary failure is truly non-critical.
CompletableFuture<Recommendation> recommendations =
        remoteSuggestions.exceptionally(error -> {
            log.warn("recommendation service unavailable", error);
            return Recommendation.empty();
        });
~~~

If product recommendations are an auxiliary feature and the API has a valid fallback, that behavior fits. However, if `remoteSuggestions` were computing taxes, inventory, payments, or order status, returning `Recommendation.empty()` similarly could mask mandatory data.

In particular, never wrap every critical task with a blanket `exceptionally(ex -> null)` and forget to attach an error status. `exceptionally` produces a **successful** new stage if the handler returns normally; downstream callers can no longer tell an error occurred unless the cause is preserved in the result or metrics.

### 5.4. thenApply and thenAccept do not receive the error branch

~~~java
// Wrong when used as a general error-handling mechanism:
future.thenAccept(value -> log.info("done: {}", value));
~~~

`thenAccept` runs only when upstream succeeds. If upstream is exceptional, the success callback does not run; **the returned stage stays exceptional**. If nobody retains that stage and no other observer exists, the error can still be forgotten.

Better:

~~~java
// Illustrative snippet: track both outcomes.
CompletableFuture<Void> tracked = future.whenComplete(
        (value, error) -> {
            if (error != null) {
                log.error("failed", error);
            } else {
                log.info("done: {}", value);
            }
        }).thenApply(ignored -> null);
~~~

Here `tracked` is retained or returned to the caller; for instance, `thenApply(ignored -> null)` converts the return value type to `Void` after success. If upstream fails, the `thenApply` branch does not run and the stage remains failed. When only observation is needed, converting to `Void` is not mandatory; `return future.whenComplete(...)` is usually enough.

### 5.5. get() and join() differ in exception types

| API | In-task error | Interrupted/cancellation |
| --- | --- | --- |
| `Future.get()` | `ExecutionException`, read `getCause()` | `InterruptedException` or `CancellationException` |
| `Future.get(timeout, unit)` | Same as above, plus `TimeoutException` when wait expires | Timeout does not cancel task automatically |
| `CompletableFuture.join()` | Typically `CompletionException` with root cause | Does not throw checked `InterruptedException`; cancellation can throw `CancellationException` |
| `CompletableFuture.get()` | `ExecutionException` | Also a `Future`, so it has checked interruption/timeout variants |

At API and logging boundaries, usually **unwrap `ExecutionException`/`CompletionException`** and then classify the root cause while preserving stack trace and context. Do not wrap every failure in `RuntimeException("failed")` without passing the cause; doing so destroys diagnostic information.

## 6. Spring @Async: return a Future so errors have a path back

### 6.1. Business errors occurring after dispatch

A Spring-managed bean:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class InvoiceWorker {
    @Async("invoiceExecutor")
    public CompletableFuture<String> generate(String id) {
        if ("BAD".equals(id)) {
            throw new IllegalArgumentException("invoice rejected");
        }
        return CompletableFuture.completedFuture("invoice/" + id);
    }
}
~~~

When invoked from **another bean through the Spring proxy** with `@EnableAsync` enabled, the method executes on the executor named `invoiceExecutor`. With return type `CompletableFuture`, target exceptions are represented as exceptional completion so callers can use `whenComplete` or `get()`. Do not call `this.generate(...)` from the same class expecting the interceptor to activate.

If you change the signature to `@Async public void generate(...)`, the caller has no Future to carry failures. Then errors go through `AsyncUncaughtExceptionHandler` (which in Spring logs by default), and you must establish a separate observation channel if the work has business impact.

### 6.2. Runnable Spring Boot 3.3.5 example

The Java 17 + Maven example below has one succeeding task and one throwing task. `ApplicationRunner` **intentionally waits with a timeout** to print a deterministic result; in a production HTTP API, return a Future, callback, or job ID instead of blocking a request similarly.

Structure:

~~~text
spring-observed-future/
├── pom.xml
└── src/main/java/com/example/failure/
    ├── AsyncFailureApplication.java
    └── InvoiceWorker.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>spring-observed-future</artifactId>
    <version>1.0.0</version>
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
            <artifactId>spring-boot-starter-aop</artifactId>
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

`src/main/java/com/example/failure/AsyncFailureApplication.java`:

~~~java
package com.example.failure;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@SpringBootApplication
@EnableAsync
public class AsyncFailureApplication {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(AsyncFailureApplication.class, args)) {
            // Demo exits after ApplicationRunner checks the Futures.
        }
    }

    @Bean("invoiceExecutor")
    ThreadPoolTaskExecutor invoiceExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("invoice-");
        pool.setWaitForTasksToCompleteOnShutdown(true);
        return pool;
    }

    @Bean
    ApplicationRunner verify(InvoiceWorker worker) {
        return args -> {
            CompletableFuture<String> ok = worker.generate("A-1");
            CompletableFuture<String> failed = worker.generate("BAD");

            AtomicInteger errorCount = new AtomicInteger();
            CompletableFuture<String> observed =
                    failed.whenComplete((value, error) -> {
                        if (error != null) {
                            errorCount.incrementAndGet();
                        }
                    });

            // Intentionally convert error into a DISPLAY status for the demo.
            CompletableFuture<String> report = observed.handle(
                    (value, error) -> error == null
                            ? "OK"
                            : "FAILED:" + root(error).getClass().getSimpleName());

            String success = ok.get(5, TimeUnit.SECONDS);
            String failureStatus = report.get(5, TimeUnit.SECONDS);

            System.out.println("SUCCESS=" + success);
            System.out.println("FAILURE_STATUS=" + failureStatus);
            System.out.println("ERROR_OBSERVATIONS=" + errorCount.get());
            System.out.println("ORIGINAL_FAILED="
                    + failed.isCompletedExceptionally());
        };
    }

    private static Throwable root(Throwable error) {
        while ((error instanceof CompletionException
                || error instanceof ExecutionException)
                && error.getCause() != null) {
            error = error.getCause();
        }
        return error;
    }
}
~~~

`src/main/java/com/example/failure/InvoiceWorker.java`:

~~~java
package com.example.failure;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class InvoiceWorker {
    @Async("invoiceExecutor")
    public CompletableFuture<String> generate(String id) {
        if ("BAD".equals(id)) {
            throw new IllegalArgumentException("invoice rejected");
        }
        return CompletableFuture.completedFuture("invoice/" + id);
    }
}
~~~

Run:

~~~bash
mvn spring-boot:run
~~~

Ignoring startup/shutdown logs, the four lines printed by `ApplicationRunner` are:

~~~text
SUCCESS=invoice/A-1
FAILURE_STATUS=FAILED:IllegalArgumentException
ERROR_OBSERVATIONS=1
ORIGINAL_FAILED=true
~~~

**Why is it deterministic?** Every variable is read **after** `report.get(5, SECONDS)`; `report` completes only after `whenComplete` increments the counter and `handle` builds the error status. Thread names, completion order between the two workers, and startup logs do not affect these four values. The business error remains on the original `failed` future, while `report` is an intentional display representation for the demo.

When moving to production, replace `errorCount` with structured logging, metrics, and job status; do not print sensitive stack traces or full order data into uncontrolled logs. The demo runs no network, DB, or transactions, so it does not yet include durability guarantees.

## 7. @Async void: without a Future, who receives the error?

With a `void` method:

~~~java
// Snippet inside a Spring-managed bean.
@Async("invoiceExecutor")
public void sendReceipt(String invoiceId) {
    throw new IllegalStateException("mail gateway failed");
}
~~~

The caller receives no Future and therefore cannot call `get()`. In Spring, uncaught errors are routed to `AsyncUncaughtExceptionHandler`. You can configure a handler:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;

@Configuration
@EnableAsync
public class AsyncErrorConfiguration implements AsyncConfigurer {
    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (error, method, parameters) -> {
            System.err.println("ASYNC_VOID_ERROR method="
                    + method.getName()
                    + ", cause=" + error.getClass().getSimpleName());
        };
    }
}
~~~

This is a complete Spring configuration class, yet it must reside in an application/context with matching async beans and executors; it is not a standalone `main` program. `System.err` is illustrative, not a production observability system. `@EnableAsync` only needs to be enabled on the right context; avoid duplicating it if already configured.

**Limitation:** the handler can log/emit metrics and trigger another handling workflow, but **cannot return a result directly to the caller**. For operations that must guarantee completion or retry, usually use `CompletableFuture<T>` (or a durable queue), since that allows combining responses, timeouts, and exception propagation. Never assume configuring a handler is enough to ensure emails/audits/payments are executed accurately.

## 8. When returning a Future to the caller: who is responsible for observing?

An anti-pattern in a controller:

~~~java
// Snippet inside a @RestController; not standalone.
@PostMapping("/invoices/{id}/generate")
public ResponseEntity<Void> generate(@PathVariable String id) {
    worker.generate(id); // Discards the Future.
    return ResponseEntity.accepted().build();
}
~~~

A `202 Accepted` response can make sense if the system **truly accepted** the request for later processing, offers status lookup, and handles rejections. However, if you merely push to an in-memory pool without a job ledger, when the task fails or the application restarts, the caller has no way to know what happened. Moreover, `worker.generate` can throw `TaskRejectedException` **right at submission time** if the pool is full; that case must be mapped to a meaningful response rather than falsely returning 202.

### 8.1. Result-waiting contract: return CompletableFuture to a layer that handles it

~~~java
// Snippet inside a Spring service/gateway.
public CompletableFuture<Invoice> generate(String id) {
    return worker.generateInvoice(id)
            .whenComplete((value, error) -> {
                if (error != null) {
                    log.error("Invoice processing failed, id={}", id, error);
                }
            });
}
~~~

Here `worker`, `Invoice`, and `log` are application-supplied components. The caller must keep returning the Future (for an MVC async response if appropriate) or attach a terminal handler. It is wrong if the gateway makes the call and **discards both the Future and status persistence**. A completion callback can log errors, yet it does not ensure the task survives an application restart.

### 8.2. Background job contract: persist durable status

Instead of treating an in-memory Future as a job ledger, use a status table in the DB, for example:

~~~text
PENDING -> RUNNING -> SUCCEEDED
                  \-> FAILED
          \-> REJECTED
          \-> TIMED_OUT / CANCELLED (per system rules)
~~~

A more reliable workflow:

1. Accept the request with an **idempotency key** and create a `PENDING` job record inside a transaction.
2. Persist/dispatch the work using a recoverable mechanism (outbox/message broker or reliable dispatcher). Respond as accepted only when the API's acceptance conditions are genuinely met.
3. Worker claims the job and transitions to `RUNNING`, executing with I/O timeouts and cancellation checks.
4. On success, record `SUCCEEDED` and the result; on failure, save `FAILED` with error code/retry status, not just a log stack trace.
5. After restart, reconciliation finds overdue `PENDING/RUNNING` jobs and decides retry/compensation while preserving idempotency of side effects.

Across multiple pods, a `CompletableFuture` in pod A's JVM is unreachable from pod B; the DB/job store must be the shared source of truth. Do not treat DB status writes and external side effects as one atomic transaction if they do not actually share a transaction; use outbox and idempotency as needed.

## 9. Handling submission rejection, timeouts, and cancellation

### 9.1. Two distinct failure moments

**Submission failure:** right when calling `executor.execute/submit` or an `@Async` proxy call, the executor may reject due to shutdown/full queue, throwing `RejectedExecutionException` (JDK) or `TaskRejectedException` (Spring). If the call never returned a Future, there is no handle to attach `whenComplete`.

~~~java
// Illustrative snippet at a Spring @Async dispatch site.
try {
    CompletableFuture<String> future = worker.generate("A-1");
    return future.whenComplete((value, error) -> recordOutcome(value, error));
} catch (org.springframework.core.task.TaskRejectedException ex) {
    recordRejected(ex);
    throw ex;
}
~~~

`recordOutcome`/`recordRejected` are hypothetical business methods. At the API layer, map rejections to `503 Service Unavailable` or `429 Too Many Requests` per contract. With silent `DiscardPolicy` or `DiscardOldestPolicy`, the `Future` can stay pending indefinitely with no visible error; prefer throwing rejection policies and monitor saturation.

**Execution failure:** the job was accepted and ran, yet the actual operation threw an exception; the Future completes exceptionally—use an observer or propagate the result to the caller. Both failure paths require separate tests.

### 9.2. A timeout does not mean the task stopped

~~~java
// Snippet on an application-owned CompletableFuture.
CompletableFuture<String> bounded =
        worker.generate("A-1").orTimeout(10, TimeUnit.SECONDS);
~~~

`orTimeout` (Java 9+) completes that `CompletableFuture` exceptionally with `TimeoutException` if still unfinished after the deadline, yet **does not automatically interrupt or stop the worker**, roll back the DB, or remove queued tasks. It returns **the same Future it was called on**, affecting other references to the same object. If you need a timeout strictly at the observation layer without mutating the upstream Future, create a separate stage or appropriate wrapper and manage its own timeout.

Similarly, `future.get(10, SECONDS)` only ends the **caller's wait**; it does not complete or cancel the Future itself.

`future.cancel(true)` is a cancellation request, with no guarantee of stopping tasks that ignore interrupts. With `CompletableFuture`, cancellation is a form of exceptional completion; the `mayInterruptIfRunning` flag does not directly control interrupting an upstream job the way `FutureTask` can.

If an HTTP client timed out while the worker is still writing an invoice, a retried request may create the invoice twice. Enforce idempotency, proper transaction boundaries, propagated I/O deadlines, and job status tracking to handle late outcomes.

## 10. Do not let exception handlers accidentally destroy error signals

### 10.1. A lot of code “catches errors” only to return success

~~~java
// Anti-pattern: turns every failure into an empty result indiscriminately.
CompletableFuture<List<Invoice>> maybe =
        invoiceFuture.exceptionally(error -> List.of());
~~~

If `List.of()` is interpreted by the API as “there are no invoices”, you are equating a *system error* with *empty data*. Use fallbacks only when business rules explicitly define them as valid responses and record degraded status.

A pattern with explicit status:

~~~java
// Snippet with record and business logic inside a service.
record JobResult<T>(String status, T value, String errorCode) { }

CompletableFuture<JobResult<Invoice>> visible = invoiceFuture.handle(
        (value, error) -> {
            if (error == null) {
                return new JobResult<>("SUCCEEDED", value, null);
            }
            return new JobResult<>("FAILED", null, classify(error));
        });
~~~

`classify` is application-defined; distinguish non-retryable business errors from retryable infrastructure failures. Avoid sending stack traces, SQL queries, or sensitive details to clients; store detailed logs separately and expose minimal error codes.

### 10.2. Unwrapping exceptions while preserving the root cause

Stages can add `CompletionException` or `ExecutionException`. When logging/measuring:

~~~java
// Helper snippet, suitable for a utility class.
static Throwable rootCause(Throwable error) {
    while ((error instanceof CompletionException
            || error instanceof ExecutionException)
            && error.getCause() != null) {
        error = error.getCause();
    }
    return error;
}
~~~

This helper unwraps only **concurrency API wrappers**, without necessarily traversing every business `cause`. For example, if a `BusinessRuleException` wraps a `SQLException` as its cause, the **business error code** may need to keep `BusinessRuleException` as the root for classification while logging the full stack trace. Do not blindly grab the deepest cause and lose business semantics.

### 10.3. Failing callbacks must also be monitored

`future.whenComplete(...)` returns **a new stage**. If a callback writing to DB/logs throws an exception, the new stage can become exceptional; observing only the original stage may miss errors from the observer itself. Therefore:

- Retain/return the stage from `whenComplete` if the callback is a mandatory part of the business flow.
- Avoid heavy blocking I/O inside completion callbacks; if durable persistence is needed, design a separate step with retries.
- Use metrics to alert on observer/persistence failures and a reconciler checking the job ledger.
- `thenApplyAsync`/`whenCompleteAsync` may need a dedicated executor; if that executor overloads, downstream stages can also fail or stall depending on rejection policy.

### 10.4. CompletableFuture.allOf() can hide component failures

~~~java
// Snippet: do not assume creating the barrier collects values.
CompletableFuture<Void> all =
        CompletableFuture.allOf(priceFuture, stockFuture, taxFuture);
~~~

`allOf` completes when **all** child Futures complete; if any fails, the barrier is also exceptional. If nobody handles `all` or the child Futures, the aggregated outcome can still be forgotten. When per-source observability is needed, attach `whenComplete`/`handle` to **each child Future** before creating the barrier, then depending on the contract either fail everything or return a partial-failure report with explicit statuses. `allOf` does not collect a list of results or all exceptions on its own.

## 11. Transactions, logging, and what “business succeeded” requires

- **Transactions:** `@Transactional` on the HTTP thread does not follow onto the worker thread. Place transactions on the Spring-proxied worker/service execution path. If the worker catches an exception and returns `completedFuture("OK")`, the transaction may not roll back as expected; govern rollback/exception propagation according to business rules.
- **Logging:** include job ID, trace ID, source, error code, and stack trace in structured logs; avoid printing “task failed” with no identifiers. Thread-local MDC/security context does not automatically cross threads without configured propagation.
- **Metrics:** track `submitted`, `running`, `succeeded`, `failed`, `rejected`, `timed_out`, `cancelled`, and `pending_over_deadline`; counting succeeded jobs alone cannot tell how many failed jobs were dropped.
- **Alerts:** alert when jobs exceed deadlines, business failure rates spike, or queues saturate. For mandatory work, an error log is rarely enough; there must be an owner/mechanism to receive and act on it.
- **Retries:** retry only appropriate errors (such as transient HTTP 503), with bounded attempts and backoff. 4xx business validation errors usually should not be blindly retried. Retries require idempotency so they do not duplicate side effects.
- **Shutdown:** when a process stops, queued tasks that never ran may never produce results; manage graceful shutdown, cancellation, and durable state for critical jobs.
- **Shared state:** a Java Future resides in one JVM's RAM; multi-instance deployments need a shared store for results, retries, and terminal states.

### Error states that must not be conflated

| Status | Example | Recommended handling |
| --- | --- | --- |
| `FAILED_BUSINESS` | Insufficient stock, invalid order | Record error code, inform caller; usually do not retry indefinitely |
| `FAILED_TRANSIENT` | Remote service 503, temporary connection drop | Bounded retry, exponential backoff + jitter |
| `REJECTED` | Saturated executor | Backpressure, 429/503, durable queue when needed |
| `TIMED_OUT` | Deadline expired while worker may still be running | Mark for reconciliation, idempotency, inspect late outcomes |
| `CANCELLED` | Future cancelled | Ensure UI/status reflects cancellation, watch for partial side effects |
| `SUCCEEDED` | Business outcome and side effects confirmed | Persist required result/metadata |

Do not use a global catch-all `Throwable` handler returning `200 OK` for every case; classify errors and return consistent contracts.

## 12. Testing and review checklist

A trustworthy test suite should cover **at least five paths**: success, business exception, timeout, submission rejection, and cancellation. Also test observer/retry failures and shutdown for critical workloads.

1. **Is the handle kept?** Does every `submit/supplyAsync/@Async` have a caller receiving and handling the Future, or an explicit watcher/job store?
2. **Are terminal failures observed?** Does `whenComplete` have an `error != null` branch, does `get/join` catch the right types, or does `handle` return an explicit failure outcome?
3. **Is a callback's returned stage discarded?** If `whenComplete` is mandatory, is the new stage monitored in case the callback fails?
4. **Are errors being swallowed?** Look for `exceptionally(ex -> null)`, `catch (Exception e) { return defaultValue; }`, unused `Future<?>`, and `thenAccept` logging only success.
5. **Are Spring signatures valid?** `@Async` returns `void`, `Future<T>`, or `CompletableFuture<T>`; method is public and called through a proxy from another bean; specific executor is identified?
6. **Submission vs. execution error?** Are `TaskRejectedException`/queue saturation checked without waiting on a Future that was never returned?
7. **Are deadlines enforced?** `get(timeout)`/`orTimeout` plus real I/O timeouts, alongside monitoring late-running tasks?
8. **HTTP contract?** Return 202 only when the request was genuinely accepted; clear responses/statuses for `FAILED/REJECTED`, no fake success?
9. **Durable status?** For critical jobs, do job ledgers, outbox/brokers, retries, idempotency, and post-restart reconciliation exist?
10. **Correlated logs?** Job ID, error code, cause, trace, and metrics, without leaking sensitive data?
11. **Real worker tests?** Do tests verify an `@Async` business exception on a pool thread through the real proxy path, not just direct method calls?
12. **allOf/partial failure tests?** Are there cases for one failing child, one pending child, deadlines, and collecting per-source statuses?

### Self-check questions

1. Why does `ExecutorService.submit` return a `Future` yet a `Callable`'s exception might not appear on stderr?
2. Is `future.isDone() == true` sufficient proof that the business task succeeded?
3. If a `CompletableFuture` fails, do `thenApply` or `thenAccept` run? Where should the error observer be attached?
4. How does `whenComplete` differ from `handle` and `exceptionally` regarding preserving vs. transforming failure state?
5. Why does `get(5, SECONDS)` expiring not mean the worker was cancelled or the DB transaction rolled back?
6. In Spring `@Async void`, where does the caller obtain exceptions? When should you switch to returning `CompletableFuture<T>`?
7. If the pool rejects right at submission, can `whenComplete` on a Future handle it if no Future was ever returned?
8. An API returns 202 without a job ID or job store—what happens if the process is killed mid-flight?
9. If an audit-logging callback fails, why might monitoring only the original Future be insufficient?
10. In what cases is `exceptionally(ex -> fallback)` permitted, and when does it turn a serious error into a wrong “success” result?

**Conclusion:** A Future is a **channel carrying results and errors**, not a “fire and forget” command. Keep or forward the handle, observe every completion branch, classify business errors, attach deadlines, and persist durable state when required. When not holding a Future, establish another explicitly designed observation mechanism; never let an exception sit captured inside a Future and vanish from the business flow.

## Official references

- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Spring Framework — Task Execution, @Async and exception handling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — AsyncUncaughtExceptionHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/interceptor/AsyncUncaughtExceptionHandler.html)
