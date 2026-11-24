# Distinguishing Fallback Value Recovery from Error-Only Observation in Spring Framework

## Goal

When an asynchronous call fails, we often want to **log/measure the error** or **supply a replacement value** so downstream steps can continue. These two goals are different: recording an error does not automatically make the result succeed, whereas returning a fallback can turn a failed future into a successful future. In Spring Framework, especially with `@Async` methods returning `CompletableFuture<T>`, this distinction determines whether the caller receives a value or an exception.

This lesson focuses on three Java `CompletableFuture`/`CompletionStage` APIs:

- **`whenComplete((value, error) -> ...)`**: observes the result or error and performs side effects like logging/metrics; if the action completes normally, the returned stage preserves **the same result or error** as the source stage.
- **`exceptionally(error -> fallbackValue)`**: runs only when the source completes exceptionally; creates a new stage that **succeeds with the replacement value** if the recovery function returns normally.
- **`handle((value, error) -> newValue)`**: runs on both success and failure, can change the type or value for **both branches**, and can also recover from an error.

After this lesson, you will be able to explain error propagation flows, pick the right operator for your goal, predict return values of stage chains, understand when a fallback inadvertently hides errors, and run a **Java 17+ + Spring Framework 6.2.x** example using Maven.

**Short rule:** `whenComplete` is for **seeing** errors; `exceptionally` or `handle` is for **deciding the outcome after an error**. A callback that logs does not constitute recovery handling.

## 1. First distinguish task errors from submission errors

In a Spring application, a service can be annotated:

```java
@Async("lessonExecutor")
public CompletableFuture<String> fetch(String key) {
    String value = remoteCall(key);
    return CompletableFuture.completedFuture(value);
}
```

This is **illustrative code that does not run standalone**: it requires a Spring bean, `@EnableAsync`, the `lessonExecutor` executor, and an application-defined `remoteCall`. When invoked through the Spring AOP proxy, the method executes in a worker of the selected executor. The caller receives a future to observe completion.

There are at least two error boundaries:

1. **Submission failure:** failing to find an executor, a closed pool, or a full queue leads to `TaskRejectedException`. This error can happen right when the caller invokes the method through the proxy, **before there is a future to attach** `exceptionally` or `whenComplete`. Protect the submission boundary if you need to catch this error.
2. **Task accepted, then fails:** `remoteCall` throws an exception in the worker or the target returns a failed future. With an `@Async` method returning `CompletableFuture`, Spring infrastructure reflects the error into **the caller's future**. From there, `CompletableFuture` operators get a chance to process the async result.

Note that `@Async void` does not give the caller a future, so you cannot call `whenComplete` or `exceptionally` on a non-existent result. Spring supports `AsyncUncaughtExceptionHandler` to observe errors not returned via a future for this kind of method.

## 2. Distinguishing source state from final business outcome

Success, exceptional, and cancellation states were explained in the lesson on the three `CompletionStage` operators. Here, the question is **whether the caller is allowed to interpret a fallback as business success?**

| Source state | Business decision | Information that must not be lost |
| --- | --- | --- |
| Succeeded with valid data, possibly `null` per contract | Use original data | Source and actual data quality. |
| Transient error, sufficiently fresh cache exists | May return fallback | Backend error, cache age, and `degraded` flag. |
| Validation, authorization, or data-integrity error | Preserve failure | Appropriate error code and cause for investigation. |
| Timeout/cancellation while I/O may still be running | Do not assume success or that the task stopped | Indeterminate status, deadline, and reconciliation capability. |

Two stages completing normally do not necessarily mean the same thing: one holds data from the primary source, while the other holds replacement data. Design domain outcomes to express that difference.

## 3. Observation is a telemetry boundary, not a recovery action

`whenComplete((value, error) -> ...)` is suitable for recording the source result/error while preserving the stage state if the callback runs normally. When defining policy, separate three events:

- `primary_failed`: the source genuinely failed before any fallback.
- `fallback_used`: the system accepted and used backup data.
- `final_failed`: the final result still failed to satisfy the contract.

An observer placed only **after** an `exceptionally` that already recovered will see a successful stage and may miss a source outage. If the observer must belong to the result the caller receives, keep/return the stage created by `whenComplete`; discarding that stage may also discard errors from the observation callback.

Logging/metrics handlers should be fast, non-blocking, and avoid throwing uncontrolled exceptions. If the source succeeds yet the observer throws, the dependent stage can fail because of the observer itself; test that condition.

## 4. Fallbacks must have an explicit acceptance contract

`exceptionally(error -> fallbackValue)` creates a new successful stage if the handler returns a value normally; **it does not resend the request**. Before implementing, decide:

1. Which error types are permitted to fall back? UI suggestions can use cache; payments and authorization checks must not return fake success.
2. Is the replacement data still valid under TTL, tenant, version, or stale-data limits?
3. Does the caller know the data source is degraded via a flag or Outcome?
4. Are the original error and fallback usage logged/measured separately, or hidden?
5. On a cache miss or disallowed error type, does the stage preserve failure with the right cause?

Do not indiscriminately use `exceptionally(ex -> null)` if `null` is not defined as a valid value: that can turn a backend failure into a delayed `NPE`. Classify exceptions and preserve appropriate causes.

## 5. Using handle to expose source and result quality

`handle((value, error) -> outcome)` runs on both branches, allowing you to return an explicit domain type for **real results, degraded results, or failures**.

The following Java 17 snippet sits inside a method that already has a variable `source` of type `CompletableFuture<String>`:

~~~java
record LookupOutcome(String value, boolean degraded, String errorCode) {}

CompletableFuture<LookupOutcome> result =
        source.handle((value, error) -> error == null
                ? new LookupOutcome(value, false, null)
                : new LookupOutcome("cached-value", true, "BACKEND_UNAVAILABLE"));
~~~

Here the failure branch assumes cache is always valid **only to illustrate data shape**; production must verify the error type and cache before allowing fallback. The stage returning `LookupOutcome(degraded=true)` is a success at the Future level, yet contains a degraded business outcome. Consumers must inspect those fields.

If no valid fallback exists, keep exceptional completion or represent `Outcome.failure` per contract. Using `handle` merely to log and `return null` loses the success value and can hide errors; `whenComplete` fits pure observation better.

## 6. Choosing operators by business responsibility

| Goal at boundary | Operator | Sign to verify |
| --- | --- | --- |
| Count source errors while still letting caller see the error | `whenComplete` before recovery | Observer sees original failure, stage stays exceptional. |
| Use cache for an allowed transient error | `exceptionally` | New stage returns valid fallback and metrics distinguish cache. |
| Map both success and failure to a domain result | `handle` | Outcome has explicit error/status/degraded fields. |
| Measure final result after all recoveries | `whenComplete` after recovery | Metric reflects final outcome, not misreported as backend failure. |
| Fallback must call another async API | `exceptionallyCompose` | Dependent stage awaits backup source without blocking `join`. |

In the next example, all three branches originate from **the same failed Future** to observe source failure, fallback, and mapped outcome separately. That makes behavior clearer than memorizing operator signatures alone.

## 7. Runnable Spring Framework example: one error, three different branches

The program below runs with **Java 17+**, Maven, and **Spring Framework 6.2.12**. We create a Spring `@Async` service with an intentionally failing business branch, then from **the same source future** create three branches:

- `observation = source.whenComplete(...)` to count how many times the error is observed.
- `recovery = source.exceptionally(...)` to return fallback `"cache:B"`.
- `handled = source.handle(...)` to return `"handled:B"` on error, while also knowing how to handle success.

We also send a successful call to prove `exceptionally` **does not alter** a successful value.

To make stdout deterministic, callbacks only update an `AtomicInteger` rather than printing from workers; `main` waits for the futures to finish and then prints in a fixed order. No `Thread.sleep` or reliance on random scheduling is needed.

### Structure

```text
async-error-recovery-demo/
├── pom.xml
└── src/main/java/example/AsyncErrorRecoveryDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>async-error-recovery-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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
                    <mainClass>example.AsyncErrorRecoveryDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/example/AsyncErrorRecoveryDemo.java`:

```java
package example;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncErrorRecoveryDemo {

    public static class LookupService {
        @Async("lessonExecutor")
        public CompletableFuture<String> lookup(String key) {
            if ("bad".equals(key)) {
                throw new IllegalStateException("Backend unavailable");
            }
            return CompletableFuture.completedFuture("remote:" + key);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {
        @Bean
        public LookupService lookupService() {
            return new LookupService();
        }

        @Bean("lessonExecutor")
        public ThreadPoolTaskExecutor lessonExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(4);
            pool.setThreadNamePrefix("lesson-");
            return pool;
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            LookupService service = context.getBean(LookupService.class);
            AtomicInteger observedErrors = new AtomicInteger();

            // An @Async invocation that intentionally fails on the worker.
            CompletableFuture<String> source = service.lookup("bad");

            // Branch 1: observe only; does not turn failure into success.
            CompletableFuture<String> observation = source.whenComplete(
                (value, error) -> {
                    if (error != null) {
                        observedErrors.incrementAndGet();
                    }
                }
            );

            // Branch 2: recover from the error with an allowed value.
            CompletableFuture<String> recovery = source.exceptionally(
                error -> "cache:B"
            );

            // Branch 3: handle both success and failure.
            CompletableFuture<String> handled = source.handle(
                (value, error) ->
                    error == null ? "handled:" + value : "handled:B"
            );

            // Success case: exceptionally preserves the original value.
            CompletableFuture<String> healthy = service.lookup("OK");
            CompletableFuture<String> successWithFallback =
                healthy.exceptionally(error -> "cache:OK");

            // Wait for each stage before printing so stdout order is deterministic.
            String recoveredValue = recovery.get(5, TimeUnit.SECONDS);
            String handledValue = handled.get(5, TimeUnit.SECONDS);
            String healthyValue = successWithFallback.get(5, TimeUnit.SECONDS);

            boolean observerStillFailed = false;
            try {
                observation.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException expected) {
                observerStillFailed = true;
            }

            System.out.println("sourceFailed="
                + source.isCompletedExceptionally());
            System.out.println("observedErrors=" + observedErrors.get());
            System.out.println("observerStillFailed=" + observerStillFailed);
            System.out.println("recoveredValue=" + recoveredValue);
            System.out.println("handledValue=" + handledValue);
            System.out.println("healthyValue=" + healthyValue);
        }
    }
}
```

Run in the `async-error-recovery-demo` directory (with JDK 17+ and Maven):

```bash
mvn -q compile exec:java
```

When the program succeeds, six lines **printed by the application** appear in exact order:

```text
sourceFailed=true
observedErrors=1
observerStillFailed=true
recoveredValue=cache:B
handledValue=handled:B
healthyValue=remote:OK
```

### Line-by-line explanation

1. `sourceFailed=true`: `lookup("bad")` throws `IllegalStateException` in the worker. The Spring proxy reflects the error into the `CompletableFuture<String>` received by the caller, so the source completes exceptionally.
2. `observedErrors=1`: `whenComplete` executes exactly once for the source's exceptional completion. `AtomicInteger` safely publishes the count across threads; after `observation.get`, `main` has waited for this callback to finish.
3. `observerStillFailed=true`: the `observation` stage **still throws `ExecutionException`** on `get`, because the observation action did not perform a fallback.
4. `recoveredValue=cache:B`: the `exceptionally` branch receives the error and returns a `String`, making the recovery stage complete normally.
5. `handledValue=handled:B`: the `handle` branch sees `error != null` and takes the recovery branch.
6. `healthyValue=remote:OK`: the `lookup("OK")` call succeeds; `exceptionally` does not run, so the original value is preserved.

**Important:** `source`, `observation`, `recovery`, and `handled` are distinct stages despite sharing the same source. `recovery` succeeding **does not rewrite** `source`'s failure status, and `observation` is not automatically healed when `recovery` succeeds. Output does not depend on ordering between worker and caller; the program waits with a timeout and prints from the `main` thread in a fixed order.

Spring `@EnableAsync` and the executor name reside on the real configuration; `LookupService` is container-managed and does not self-invoke `this.lookup(...)`. The methods/signatures are compatible with Spring AOP proxies. If the environment cannot download dependencies or tasks fail to finish within 5 seconds, the program may report an error instead of these six lines; that is not a change in operator contract.

## 8. Operator chaining order changes which errors are observed

This is the most critical part when building a system that needs both monitoring and fallbacks.

### Observing before recovery

```java
CompletableFuture<String> answer = source
    .whenComplete((value, error) -> {
        if (error != null) {
            metrics.countBackendFailure();
        }
    })
    .exceptionally(error -> "cache");
```

This is an application snippet with `source` and `metrics`; not standalone. `whenComplete` sees the **original error** to update metrics. `exceptionally` afterward receives the error and turns it into `"cache"` if needed. `answer` is a successful stage when the fallback succeeds.

### Recovering first and observing afterward

```java
CompletableFuture<String> answer = source
    .exceptionally(error -> "cache")
    .whenComplete((value, error) -> {
        if (error != null) {
            metrics.countBackendFailure();
        }
    });
```

If the source error was already converted into a successful fallback by `exceptionally`, the subsequent callback receives `error == null` and does not count the backend failure. If the monitoring goal is the real backend failure rate, this order **hides the cause at the post-recovery observation layer**.

That does **not** mean a downstream operator can never see an error: if the fallback itself throws an exception or another stage throws, the downstream `whenComplete` can see the new error. Clearly define metrics as “backend failures”, “fallback used”, “final request failures”, or “user-visible failures”; they are not identical.

### Pipeline illustration

```text
Backend failure
     |
     +--> whenComplete(log backend failure)
                   |
                   v
             exceptionally(cache)
                   |
                   v
             SUCCESS("cache") ----------> caller

Backend failure
     |
     +--> exceptionally(cache)
                   |
                   v
             SUCCESS("cache")
                   |
                   v
             whenComplete(log final outcome)
                error == null ----------> caller
```

In practice, measure **both source errors and fallback usage rates**. A caller receiving a replacement value does not mean the backend is healthy or needs no investigation.

## 9. How to log while keeping the failure?

Use `whenComplete` and **return that stage**, without turning the error into a value:

```java
return service.lookup(key)
    .whenComplete((value, error) -> {
        if (error != null) {
            logger.error("Async lookup failed for key={}", key, error);
        }
    });
```

This snippet sits inside a method with `service`, `key`, and `logger`; not standalone. If the source fails, the returned stage still fails (when logging does not throw). The caller can still use `get()`/`join()` or controller exception mapping to see the failure.

Do not write:

```java
return service.lookup(key)
    .handle((value, error) -> {
        if (error != null) {
            logger.error("Failed", error);
        }
        return null;
    });
```

This only illustrates a design flaw and also does not run standalone. `handle` returns `null` for **both success and failure**, causing the caller to receive a successful future with `null`; it both loses the normal value and swallows the failure cause. With a `Result<T>` API, this can lead to `NullPointerException` in later layers and erases the initial incident context.

If you want to *selectively* continue throwing after `handle`, rethrow properly (for example using `CompletionException`) and understand that the new stage remains failed, not recovered. More simply, use `whenComplete` for observation.

## 10. Conditional fallback: recover only acceptable errors

Not every error deserves to be turned into success. For example, an unreachable backend may allow cache, whereas invalid credentials, business-rule violations, inconsistent data, or security errors may need to propagate upward.

```java
CompletableFuture<String> controlled = source.exceptionally(error -> {
    Throwable root = error;
    while (root instanceof java.util.concurrent.CompletionException
            && root.getCause() != null) {
        root = root.getCause();
    }

    if (root instanceof TransientBackendException) {
        return "stale-cache-value";
    }

    throw new java.util.concurrent.CompletionException(root);
});
```

This is an illustrative snippet, where `TransientBackendException` is an application-defined error type. `CompletionException` may wrap the cause when async stages propagate errors; other implementations may create different wrappers, so classification must be tested against your project's own pipeline. Do not treat every `Throwable` as transient. If fallback fails, throwing from the handler leaves the new stage failed rather than silently returning null.

For sensitive business operations, use a result type with metadata:

```java
record LoadResult(String value, boolean fallbackUsed) {}

CompletableFuture<LoadResult> result = source.handle(
    (value, error) -> error == null
        ? new LoadResult(value, false)
        : new LoadResult("cached", true)
);
```

The snippet above is Java 17 (requiring `source` of type `CompletableFuture<String>`). If a backup value is unacceptable for the current error, the handler must **propagate the failure** instead of always returning `"cached"`.

## 11. Asynchronous fallback: `exceptionallyCompose` vs. `exceptionally`

`exceptionally` requires the callback to return **a value `T`**; if the fallback itself must invoke another async API, you can use `exceptionallyCompose` (available in Java 17) to obtain a `CompletionStage<T>` and “flatten” it.

Example:

```java
CompletableFuture<String> answer = primary.loadAsync(key)
    .exceptionallyCompose(error -> secondary.loadAsync(key));
```

This is an architectural snippet; both `primary` and `secondary` must provide APIs returning `CompletableFuture<String>` or a compatible stage, with proper timeouts, quotas, and idempotency designed. The secondary task is invoked only when primary fails. If secondary also fails, the combined stage fails too unless another recovery step exists.

**Do not** write a fallback that blocks a thread just to fetch an async value:

```java
CompletableFuture<String> answer = primary.loadAsync(key)
    .exceptionally(error -> secondary.loadAsync(key).join());
```

This snippet illustrates an anti-pattern when running on a small pool or an I/O-heavy system. Calling `.join()` inside the callback can tie up the thread until secondary finishes, reducing throughput or causing deadlock if secondary needs the same worker. `exceptionallyCompose` preserves a cleaner async chain.

If the fallback must switch to another executor for heavy work, consider `exceptionallyAsync(fn, executor)` or `exceptionallyComposeAsync(fn, executor)` per Java 17 API, rather than assuming non-async callbacks pick a separate pool.

## 12. `whenCompleteAsync`, `handleAsync`, and callback threads

Common variants:

| API | Where is the callback invoked? | When to use |
| --- | --- | --- |
| `whenComplete(action)` | May run on the stage-completing thread or registering/completing helper thread if stage is already done. | Lightweight, non-blocking observation. |
| `whenCompleteAsync(action)` | Dispatches action through the stage/JDK default async executor. | Want action scheduled asynchronously and default executor is acceptable. |
| `whenCompleteAsync(action, executor)` | Runs action on the provided executor. | Want pool control for logging/audit callbacks. |
| `exceptionally(fn)` | Executes per non-async completion policy; does not schedule an extra worker itself. | Simple and fast fallback. |
| `exceptionallyAsync(fn, executor)` | Runs fallback on the specified executor. | Fallback has logic requiring resource isolation. |
| `handleAsync(fn, executor)` | Runs the success/failure handler via the specified executor. | Need outcome transformation without occupying the completion thread. |

The presence of Spring `@Async("lessonExecutor")` **does not mean** all subsequent chained stages automatically use `lessonExecutor`. `CompletableFuture` has its own executor rules: `...Async(...)` overloads without an executor parameter typically use the stage/JDK default facility (usually the common pool). For blocking workloads or sensitive data, specify the executor and context propagation explicitly.

Do not place long blocking I/O inside `whenComplete` if it runs directly on the thread completing a critical Future. The callback can delay dependent stage completion and keep Spring workers busy. For logging, consider non-blocking/queued logging mechanisms and monitor errors in the observation pipeline itself.

## 13. When `whenComplete`/`exceptionally` hide or alter errors unexpectedly

### Case 1 — Logging callback throws on success

```java
CompletableFuture<String> ok =
    CompletableFuture.completedFuture("OK");

CompletableFuture<String> afterLog = ok.whenComplete(
    (value, error) -> {
        throw new IllegalStateException("Logging is down");
    }
);
```

This plain Java snippet creates `afterLog` in a failed state, even though `ok` remains successful. That is why side-effect observers must be designed reliably, especially external audit/logging that can fail.

### Case 2 — Recovery callback fails itself

```java
CompletableFuture<String> afterFallback = source.exceptionally(
    error -> {
        throw new IllegalArgumentException("Cache is not ready");
    }
);
```

If `source` failed, `afterFallback` fails with the cache error itself. Adding `exceptionally` does not automatically yield a successful result; recovery succeeds only when the fallback returns normally.

### Case 3 — `null` recovery accidentally turns failure into success

```java
CompletableFuture<String> masked = source.exceptionally(
    error -> null
);
```

With `String` being a reference type, `masked.join()` can return `null` without throwing. If the caller does not expect null, you have turned an explicit backend failure into a hard-to-trace NPE later. Define a concrete fallback contract, or let the failure propagate for upper layers to handle.

### Case 4 — Observing only and then still calling `thenApply`

```java
CompletableFuture<String> transformed = source
    .whenComplete((value, error) -> audit(error))
    .thenApply(String::toUpperCase);
```

If `source` failed, `whenComplete` still propagates the failure and `thenApply` **does not run**; `transformed` remains failed. If `thenApply` must always receive a value (unless fallback also fails), place `exceptionally` or `handle` **before** the transformation step.

## 14. Recovery does not mean all side effects were handled

### In Spring MVC

If a controller receives a recovered `CompletableFuture<String>`, the MVC/API layer may return a success response with the fallback. This makes sense for services where caching is acceptable, yet it should not turn a payment failure or authorization check error into a fake HTTP 200. Distinguish “result from primary” vs. “result from fallback” in domain/observability whenever it affects user decisions.

A controller calling `future.get()` or `join()` immediately still blocks the request thread even if the service is `@Async`. The async HTTP layer has its own contract; a future alone does not guarantee non-blocking end-to-end request handling.

### Transactions and retries

If a worker already wrote partially to the database and then threw an exception, `exceptionally` returning a fallback **does not roll back** transactions or undo side effects. Rollback depends on transaction boundaries/isolation and business code itself. `@Transactional` on the caller does not automatically propagate across `@Async` workers; check proxies and transactions on the execution thread.

Nor does a fallback **retry** the backend. True retry means re-invoking, which requires bounded attempts, timeouts, backoff, idempotency, an overall deadline, and avoiding saturating an overloaded pool. When a task has already produced side effects, retrying can duplicate them without protection.

### Timeouts and cancellation

`Future.get(timeout, unit)` only limits **how long the caller waits**; it does not cancel the worker automatically. `CompletableFuture.orTimeout(...)` can complete the future itself with a timeout exception while pending; if a subsequent `exceptionally` returns a fallback, the caller receives the replacement value while the underlying worker continues running. `completeOnTimeout(...)` puts a fallback directly into the future if not done by the deadline, and likewise does not force the worker to stop.

`CompletableFuture.cancel(true)` does not guarantee interrupting the computation that completes it. If the user no longer needs the result, implement cooperative cancellation policies and real I/O client timeouts. Do not assume “recovered” means resources were reclaimed.

### Context and thread safety

`@Async` is a thread boundary. MDC logging, `SecurityContext`, request attributes, transactions, and many `ThreadLocal` values from the caller do not automatically transfer to the worker. Non-async `whenComplete` callbacks may also run on another stage-completing thread; if correlation IDs are needed, use intentional context propagation and clean/restore in `finally`. Never store user request information in a mutable singleton field for async logging.

## 15. Designing error and fallback observability in production

Separate these signals:

| Metric | Meaning | Why keep separate? |
| --- | --- | --- |
| `primary_failure_total` | Backend/source task failed before recovery. | Fallbacks can make the final request succeed; measuring only final errors misses outages. |
| `fallback_attempt_total` | Attempted to fetch backup value. | Shows how heavily the system relies on fallbacks. |
| `fallback_success_total` | Fallback returned a valid value. | Measures true recovery effectiveness. |
| `fallback_failure_total` | Fallback itself failed. | Distinguishes double degradation. |
| `final_request_failure_total` | Final caller still received an error. | Measures real impact on users. |
| `fallback_data_age` | Age of cached/stale value if applicable. | Prevents unsuitable backup data from being treated as fresh. |

If metrics are recorded only **after** `exceptionally`, upstream failures may no longer appear as `error`. You typically need to observe the source before recovery, then measure the final outcome after fallback. Never let a metric sink or logger stall business thread pools or throw unexpected exceptions.

You can express the final outcome with a domain type instead of masking the source:

```java
record FetchOutcome(String value, boolean degraded) {}

CompletableFuture<FetchOutcome> finalResult = source.handle(
    (value, error) -> error == null
        ? new FetchOutcome(value, false)
        : new FetchOutcome("cached", true)
);
```

This is a Java 17 snippet; the business layer must define which error cases allow `"cached"` and whether backup data is valid. If no reliable fallback exists, let the failure keep propagating to the appropriate handling layer.

## 16. Common mistakes

| Mistake | Consequence | Solution |
| --- | --- | --- |
| Using `whenComplete` to log and thinking the error is fixed. | Caller continues receiving failure. | Use `exceptionally`/`handle` if you **genuinely want** to return a fallback. |
| Using `handle` just to log and `return null`. | Swallows errors, loses success values, causes delayed NPEs. | Use `whenComplete` to observe while preserving the outcome. |
| Using `exceptionally(ex -> null)` for every error. | Failures turn into null successes. | Define an explicit fallback contract or let errors propagate. |
| Falling back on every exception, including validation/security. | Masks business errors and can break security. | Recover only acceptable error types. |
| Attaching metrics after recovery and counting only `error != null`. | Backend outages hidden by fallbacks go unseen. | Count source errors before fallback, and also measure final outcomes. |
| Thinking `exceptionally` mutates the source future itself. | Other consumers holding the source still see failure. | Return/use the post-recovery stage; understand each stage is separate. |
| Thinking `exceptionally` retries automatically. | Does not re-call the backend; result comes only from fallback. | If retries are needed, design bounded retries with idempotency. |
| Calling `.join()` inside fallback to wait on another API on a small pool. | Ties up workers, can deadlock. | Use `exceptionallyCompose` for async fallbacks. |
| Putting long logging I/O in `whenComplete`. | Holds the stage-completing thread and increases latency. | Keep observers lightweight, or isolate onto a controlled executor. |
| Assuming non-async callbacks always run on the main thread. | Wrong context/MDC, broken thread safety. | Understand completion threads and context propagation. |
| `@Async void` while trying to call `exceptionally` from caller. | No result handle exists. | Return a Future or use `AsyncUncaughtExceptionHandler`. |
| Ignoring task submission errors. | `TaskRejectedException` occurs before the callback chain. | Catch at submission time and manage overload/rejection. |
| Treating successful fallback as meaning the worker stopped. | Old task/side effects may keep running. | Separate completion policy from cancellation and I/O timeouts. |

## 17. Code review checklist

1. **Observing or replacing the result?** For logging/metrics only, `whenComplete`; for a success fallback, `exceptionally`/`handle`.
2. **Which stage is returned to the caller?** Original or recovery stage? Was an observation stage dropped so callback exceptions go unnoticed?
3. **Is the success branch altered?** `exceptionally` preserves success; `handle` runs on both branches.
4. **Which errors are recovered?** Are transient, validation, auth, cancellation, and timeout distinguished rather than catching all `Throwable`?
5. **Is the fallback meaningful to the business?** Is backup data valid, sufficiently fresh, and marked degraded?
6. **Are upstream failures monitored?** Logging/metrics before recovery, counting fallback usage and final outcomes?
7. **Can callbacks block or throw?** `whenComplete` throwing on success fails the new stage; a throwing fallback fails the recovery stage.
8. **Are Spring async boundaries accurate?** Spring-managed bean, `@EnableAsync`, call via proxy, executor qualifier?
9. **Are submission errors and `@Async void` handled?** They do not necessarily enter a Future pipeline.
10. **Is an async fallback needed?** Prefer `exceptionallyCompose` when fallback returns another stage, avoiding blocking `join`.
11. **Where are context and transactions managed?** Workers/callbacks do not automatically inherit caller `ThreadLocal`s.
12. **What should the final caller see?** True success, degraded success, or error; never use a fake HTTP 200 to hide critical errors.

## 18. Practice quiz

**Question 1.** `source` finishes with `IllegalStateException`. Does `source.whenComplete((v,e) -> log(e))` make `join()` on the new stage return a value?

**Answer:** No. If the logging callback finishes normally, the new stage preserves the source's exception; `join()` still throws.

**Question 2.** Does `source.exceptionally(e -> "cache")` change `source.isCompletedExceptionally()` to false?

**Answer:** No. Recovery creates a new dependent stage; `source` stays failed. Only the recovery stage succeeds with `"cache"`.

**Question 3.** `source` succeeds with `"OK"`. What does `source.exceptionally(e -> "cache")` return?

**Answer:** `"OK"`. The fallback callback does not run when the source succeeds.

**Question 4.** A `handle` callback is written as `(v,e) -> null` just to print errors. What happens?

**Answer:** The handler runs for every outcome and the resulting stage succeeds with `null` if the handler does not throw; this is not “observation only”—it can hide failures and lose success values.

**Question 5.** `whenComplete` throws an exception when the source succeeded. Is the new stage still successful?

**Answer:** No. The dependent stage fails with the callback's exception. If the source had already failed, per `whenComplete` rules, the source error takes precedence when the callback also throws.

**Question 6.** When you want to record both backend errors and fallback success rates, where should logs/metrics be placed?

**Answer:** Observe source errors **before** recovery and measure fallback outcomes **afterward**. Observing only after recovery means backend errors may already have been converted into successes.

**Question 7.** A fallback must call another async API. Is `exceptionally(error -> secondary.getAsync().join())` optimal?

**Answer:** Usually not, because `.join()` can block the completion thread. Use `exceptionallyCompose` and manage timeouts/executors properly.

**Question 8.** An `@Async` method returning `void` fails on a worker. What does the caller attach `whenComplete` to?

**Answer:** There is no returned Future to attach to. You need an exception handler/logging for `@Async void`, or change the method contract to return `CompletableFuture` if the caller must observe it.

**Question 9.** `get(timeout)` expires and an `exceptionally` after `orTimeout` returns cache. Does that mean the I/O worker stopped?

**Answer:** No. Future completion/fallback and I/O task lifecycle are separate; timeouts/cancellation are needed at the execution layer.

### Key takeaway

**Observing errors only** and **recovering with a replacement value** are two distinct decisions. `whenComplete` helps with logging/metrics and normally preserves the outcome; `exceptionally` replaces failures with a value; `handle` can produce a new outcome on both success and failure. In Spring `@Async`, observe the exact stage the caller receives, configure executors explicitly, and separate recovery policies from timeouts, retries, transactions, and side effects. A good fallback is business-meaningful, bounded, monitored, and never erases traces of the source error.

### Official references

- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): contracts for `whenComplete`, `exceptionally`, `handle`, `exceptionallyCompose`, `get`/`join`, and completion state.
- [Java SE 17 — CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html): rules for dependent stages and callback errors.
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): `@Async`, executor selection, `Future`, and exception management.
- [Spring Framework 6.2 — @Async Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/Async.html): return types, proxies, and futures observed by callers.
