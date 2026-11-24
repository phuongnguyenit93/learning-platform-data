# CompletableFuture, Callbacks, and Error Propagation in Testing

In Spring Boot, asynchronous programs often return a `CompletableFuture`, register callbacks with `thenApply`/`thenAccept`/`whenComplete`, or use `@Async` to run on an executor. The dangerous trap is that **a test can PASS before the work finishes**. An assertion throwing an error inside a callback on another thread does not automatically fail the JUnit test if the test does not **wait for and check the right completion stage**.

Example of a broken test:

```java
@Test
void testXanhGia() {
    CompletableFuture.supplyAsync(() -> "wrong")
            .thenAccept(value -> assertEquals("expected", value));

    // The test method finishes immediately; no one observes the future
    // of thenAccept. The AssertionError may be held inside the
    // exceptional completion of the abandoned stage.
}
```

The code above is only a snippet to illustrate the anti-pattern (requires imports). The right way is to **keep the stage returned by the callback** and wait for that stage to complete with `get(timeout, unit)`, or use `join()` with an explicitly managed deadline:

```java
@Test
void testThucSuChoCallback() throws Exception {
    CompletableFuture<Void> checked =
            CompletableFuture.completedFuture("expected")
                    .thenAccept(value ->
                            assertEquals("expected", value));

    checked.get(5, TimeUnit.SECONDS);
    // If the callback throws AssertionError, get() throws
    // ExecutionException and JUnit reports the test FAILED.
}
```

This lesson belongs to the **Async and Scheduling** group of **Spring Boot - testing**. We will learn `CompletableFuture` composition operations, callback semantics on success/failure, how to receive errors via `get` and `join`, what gets hidden by `exceptionally`/`handle`, timeout/cancellation, `@Async` proxies, executors, and scheduled jobs. The hands-on section features a **Java 17 + Spring Boot 3.5 + JUnit Jupiter** project, including pure Java unit tests and integration tests with real Spring `@Async`, **requiring no Docker or Internet access**.

## 1. How does CompletableFuture differ from Thread and traditional Future?

`CompletableFuture<T>` is both a `Future<T>` (can wait for a result) and a `CompletionStage<T>` (can compose processing steps). It has observable states:

- **Incomplete**: no result yet. `isDone() == false`.
- **Completed normally**: has a value, including `null`; `get()/join()` returns the value.
- **Completed exceptionally**: an error is stored in the future. `get()/join()` throws the corresponding exception.
- **Cancelled**: cancelled state, also considered an exceptional completion; `isCancelled() == true`.

`isDone() == true` **does not mean success**: a future that threw an exception or was cancelled is also done. To know the outcome, you must observe `get()/join()`, `isCompletedExceptionally()`, or verify that the stage completed validly.

```text
CompletableFuture<T>
       |
       +-- incomplete
       |       |
       |       +-- complete(value) ------------> normal completion
       |       |
       |       +-- completeExceptionally(ex) --> exceptional completion
       |       |
       |       +-- cancel(...) ----------------> cancelled
       |
       +-- dependent stages:
               thenApply / thenCompose / thenCombine
               thenAccept / whenComplete
               exceptionally / handle
```

A stage can complete asynchronously via execution on another executor/thread or be completed immediately by code calling `complete`. `thenApply` **does not guarantee execution on a separate thread**: the callback may run on the thread that completed the upstream stage or on the thread registering the callback if the stage is already done. Use `thenApplyAsync` with a specified `Executor` when you need to control where it runs, and remember that `Async` overloads without an executor typically use the default asynchronous facility (or the common pool in standard CompletableFuture).

**Do not equate CompletableFuture with Spring `@Async`**:

- `CompletableFuture.supplyAsync(...)` uses a Java executor and does not require Spring.
- `@Async` is Spring's AOP/proxy interceptor; the method is dispatched to a Spring `TaskExecutor` when invoked through the proxy.
- An `@Async` method can **return `CompletableFuture.completedFuture(...)` inside the worker thread**. The caller receives a future representing the executor's execution, not "already finished immediately because it returned completedFuture internally".
- `@Scheduled` is a mechanism for invoking tasks on a schedule, and does not automatically put errors into a future returned to a JUnit test.

## 2. How do errors propagate through stages?

### 2.1. Successful pipeline

```java
CompletableFuture<String> ready =
        CompletableFuture.completedFuture("  order-7  ")
                .thenApply(String::trim)
                .thenApply(String::toUpperCase);

assertEquals("ORDER-7", ready.join());
```

`thenApply` callbacks run only when upstream completes normally. If an upstream stage fails, downstream `thenApply` callbacks **do not run** and the dependent stage normally also completes exceptionally. If the callback itself throws, the error does not necessarily appear at the line where the callback was registered; it is held in the **returned stage**.

### 2.2. Callback throws on its own

```java
CompletableFuture<String> source =
        CompletableFuture.completedFuture("invoice-A");

CompletableFuture<String> mapped =
        source.thenApply(value -> {
            throw new IllegalArgumentException("mapping-invalid");
        });

assertEquals("invoice-A", source.join());

CompletionException failure = assertThrows(
        CompletionException.class, mapped::join);
assertInstanceOf(
        IllegalArgumentException.class, failure.getCause());
```

**Which stage owns the error?** `source` still succeeds; **`mapped`** fails. If a test only calls `source.join()` and ignores `mapped`, callback assertions or mapping errors will be hidden. This is a common mechanism causing false-positive tests.

### 2.3. `thenApply`, `thenCompose`, `thenCombine`

| API | When does it run? | Result | When upstream fails |
|---|---|---|---|
| `thenApply(fn)` | Upstream succeeds | `CompletableFuture<U>` of transformed value | Callback does not run; downstream exception |
| `thenAccept(consumer)` | Upstream succeeds | `CompletableFuture<Void>` | Callback does not run; downstream exception |
| `thenRun(runnable)` | Upstream succeeds | `CompletableFuture<Void>` | Callback does not run; downstream exception |
| `thenCompose(fn)` | Upstream succeeds | Flattens a subsequent stage into one future | Error chain is forwarded |
| `thenCombine(other, fn)` | Both upstreams succeed | Combines results of two stages | If one fails, combined stage fails |
| `allOf(stages...)` | All stages finish | `CompletableFuture<Void>`, does not contain result list | If any stage fails, `allOf` completes exceptionally |
| `anyOf(stages...)` | First stage finishes | `CompletableFuture<Object>` | May succeed or fail depending on the first stage |

`thenCompose` is commonly used when the callback returns another `CompletableFuture` and you do not want `CompletableFuture<CompletableFuture<T>>`:

```java
CompletableFuture<String> result =
        CompletableFuture.completedFuture("O-1")
                .thenCompose(id ->
                        CompletableFuture.completedFuture("DONE:" + id));
assertEquals("DONE:O-1", result.join());
```

Use `allOf` when you want to wait for **all branches**, but you must handle a failing branch and collect each branch's result afterward. Do not assume `allOf` returns `List<T>` or immediately cancels remaining tasks when one branch fails. Inspect each stage and apply a deadline when needed.

## 3. `get`, `join`, `ExecutionException`, and `CompletionException`

This part is especially important in JUnit.

| Method | When normal | When stage fails | Timeout? | Checked exceptions |
|---|---|---|---|---|
| `future.get()` | Returns T, waits indefinitely if incomplete | `ExecutionException` with `getCause()` as root error | No | `InterruptedException`, `ExecutionException` |
| `future.get(5, SECONDS)` | Returns T before deadline | `ExecutionException` | **Yes**, throws `TimeoutException` if wait expires | Adds `TimeoutException` |
| `future.join()` | Returns T, waits indefinitely if incomplete | Typically `CompletionException` with root cause | No | No checked exception declaration required |
| `future.orTimeout(...).join()` | Result or root error | `CompletionException` (cause may be `TimeoutException`) | Yes, **mutates future state** | Unchecked |
| `future.completeOnTimeout(default, ...)` | Result or fallback | Can complete **normally** with fallback | Yes, **completes future with value** | No |

### 3.1. JUnit with `get(timeout)`

```java
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IllegalStateException("no-stock"));

ExecutionException error = assertThrows(
        ExecutionException.class,
        () -> failed.get(5, TimeUnit.SECONDS));

assertInstanceOf(
        IllegalStateException.class, error.getCause());
assertEquals("no-stock", error.getCause().getMessage());
```

`failedFuture` has been available since Java 9. Using `get(timeout)` makes the error actually surface **on the test thread** and prevents the test from hanging indefinitely if the producer never completes. When a callback throws `AssertionError`, `get` can still throw `ExecutionException`, whose cause is the assertion failure.

### 3.2. JUnit with `join()`

```java
CompletionException error = assertThrows(
        CompletionException.class,
        () -> CompletableFuture.<String>failedFuture(
                new IllegalStateException("no-stock")).join());

assertInstanceOf(
        IllegalStateException.class, error.getCause());
```

`join` is convenient in code but **has no default timeout**; integration tests involving networking or schedulers should not use an unbounded `join`. You can use `get(5, SECONDS)` at test boundaries, or `orTimeout(5, SECONDS)` when you **want that future itself** to complete exceptionally at the deadline.

### 3.3. Unwrapping wrapper layers properly

A Future/stage chain can wrap exceptions in `CompletionException` or `ExecutionException`. There can be multiple wrapper layers when code catches and rethrows. Do not hard-code a stack trace string or always force `getCause().getCause()` if APIs can change.

```java
static Throwable unwrap(Throwable error) {
    Throwable current = error;
    while ((current instanceof CompletionException
            || current instanceof ExecutionException)
            && current.getCause() != null) {
        current = current.getCause();
    }
    return current;
}
```

The snippet requires imports `java.util.concurrent.CompletionException` and `ExecutionException`. Unwrap only the exact wrapper types needed; do not blindly swallow any `Throwable`. In the demo below we assert known causes directly, instead of hiding failures behind a complex helper.

### 3.4. Distinguishing wait timeout from computation timeout

`future.get(100, MILLISECONDS)` throws `TimeoutException` **to the waiter**, while the future **may still be running**; calling `get(5, SECONDS)` afterward can still return the result.

`future.orTimeout(100, MILLISECONDS)` schedules **completing that future itself exceptionally** if not yet done. It does not guarantee cancelling a TCP operation or interrupting a computing worker.

`future.completeOnTimeout("fallback", 100, MILLISECONDS)` completes **the future itself** with a fallback value when late; hence the test receives the fallback and the future reports no error, yet the backend/worker may continue producing side effects. Do not use a fallback to claim a request was cancelled or rolled back.

`cancel(true)` on `CompletableFuture` sets the cancelled state if not yet done, but the Java 17 Javadoc notes `mayInterruptIfRunning` **has no interrupt effect in this implementation**. To stop real resources, you must design cancellation/interrupt/timeout at the executor, HTTP/DB client, and business layers.

## 4. Observing callbacks, transforming callbacks, and recovering callbacks

### 4.1. `whenComplete`: observation, not recovery

`whenComplete((value, error) -> ...)` receives both success and error. It returns **a new stage** with the same outcome as upstream if the callback does not throw. If the callback throws when upstream succeeded, the **returned stage** completes exceptionally with the callback's error. If upstream already failed and the callback also throws, per the Java 17 API, the upstream failure **takes precedence** in the returned stage.

```java
CompletableFuture<String> upstream =
        CompletableFuture.completedFuture("OK");

CompletableFuture<String> observed =
        upstream.whenComplete((value, failure) -> {
            if (failure == null) {
                throw new IllegalArgumentException("observer-broken");
            }
        });

assertEquals("OK", upstream.join());

CompletionException error = assertThrows(
        CompletionException.class, observed::join);
assertInstanceOf(
        IllegalArgumentException.class, error.getCause());
```

**Common mistake:** calling `upstream.whenComplete(logOrAssert)` and discarding the result, then only calling `upstream.join()`. If the callback throws an error, the test will miss the observer's failed stage.

### 4.2. `exceptionally`: recovering on failure

```java
CompletableFuture<String> upstream =
        CompletableFuture.failedFuture(
                new IllegalStateException("gateway-down"));

CompletableFuture<String> recovered =
        upstream.exceptionally(ex -> "FALLBACK");

assertEquals("FALLBACK", recovered.join());
assertTrue(upstream.isCompletedExceptionally());
assertFalse(recovered.isCompletedExceptionally());
```

`exceptionally` creates a **new successful future** if the recovery function returns a value. When production code only logs and returns a fallback, a test that only asserts the fallback can mask an upstream failure if business rules require failing. Verify **whether fallback is permitted**, metrics/retry/alerting, and service state.

### 4.3. `handle`: transforming both success and failure

```java
CompletableFuture<String> outcome =
        CompletableFuture.<String>failedFuture(
                new IllegalArgumentException("bad-input"))
            .handle((value, error) ->
                    error == null ? "OK:" + value : "FAILED");

assertEquals("FAILED", outcome.join());
```

`handle` always runs when upstream completes (normally or exceptionally) and can turn an error into a successful value. If the handler itself throws an exception, the **returned stage** fails again. Use `whenComplete` for logging/metrics/observation; `handle` when intentionally converting either outcome into a value; `exceptionally` when you only want recovery on the error branch.

### 4.4. `thenAccept` and assertions inside callbacks

A JUnit assertion throws `AssertionError`, not a regular `Exception`; `CompletableFuture` completes the dependent stage exceptionally.

```java
CompletableFuture<Void> checked =
        CompletableFuture.completedFuture("actual")
                .thenAccept(value ->
                        assertEquals("expected", value));

// MUST await the stage returned from thenAccept.
ExecutionException failure = assertThrows(
        ExecutionException.class,
        () -> checked.get(5, TimeUnit.SECONDS));
assertInstanceOf(AssertionError.class, failure.getCause());
```

This is **a test intentionally expecting the callback to fail**, not a recommendation to write failing assertions. In normal tests, write the proper assertion and call `checked.get(5, SECONDS)`; then a failing callback naturally fails the test.

## 5. Avoiding false positives when testing asynchronously

### 5.1. A `@Test void` finishing does not mean the worker finished

```java
@Test
void khongNenViet() {
    service.runAsync().thenAccept(result -> {
        assertEquals("expected", result);
    });
    // Not awaiting the returned future -> JUnit can falsely report PASS.
}
```

This code is an anti-pattern (hypothetical service). When the test method returns, JUnit considers the body finished. It does not automatically join futures, wait for the thread pool to drain, or catch errors from abandoned callbacks.

The right way:

```java
@Test
void dung() throws Exception {
    CompletableFuture<Void> assertionStage =
            service.runAsync().thenAccept(result ->
                    assertEquals("expected", result));

    assertionStage.get(5, TimeUnit.SECONDS);
}
```

### 5.2. Use `CountDownLatch` instead of sleeping to guess

To test a blocked task, use **two latches**:

```text
JUnit thread                Worker thread
     |                           |
     +--- call async method ---->|
     |                           +-- started.countDown()
     |                           +-- release.await()
     |
     +--- started.await(...)  <--+
     +--- assert get(timeout) throws TimeoutException
     +--- release.countDown() ---> worker resumes
     +--- assert get(5s) returns actual result
```

Strength: the test knows the worker **entered the region under test** before attempting timeout. Use `finally` to release the latch even if an assertion fails, preventing a hung worker from affecting later tests. Only use bounded timeouts; do not sleep 2 seconds just to "be sure the worker started".

### 5.3. `assertTimeoutPreemptively` is not the default solution

JUnit's `assertTimeoutPreemptively` can run the executable on another thread, causing issues with Spring TestContext's **ThreadLocal-bound test-managed transaction**: DB operations on the new thread may not participate in the test thread's transaction rollback. For Spring integration tests, it is usually better to use **`future.get(timeout)`** to wait on the test thread, or `assertTimeout` (non-preemptive) for code guaranteed to finish.

`assertTimeout` cannot cut short an indefinitely hung operation; therefore, for async/network calls, use **deadlines on the future/client** instead of only an outer assertion timeout.

### 5.4. Do not treat a latch countdown as an error having been propagated

`latch.countDown()` only marks an event. It does not automatically propagate a worker's `Throwable`. For callbacks under test, it is better to put the outcome into a `CompletableFuture` and await the stage. If you only have a callback-style API, create a future bridge:

```java
CompletableFuture<String> bridge = new CompletableFuture<>();

legacyApi.fetch(
        value -> bridge.complete(value),
        error -> bridge.completeExceptionally(error));

assertEquals("value", bridge.get(5, TimeUnit.SECONDS));
```

This is a snippet: `legacyApi` is a hypothetical API with success/error callbacks; it does not run standalone. The bridge should have a timeout and an exactly-once completion policy; if the API invokes the callback multiple times, only the first `complete` succeeds. If the callback may run on an event loop, do not block the event loop with `join()` inside the callback.

## 6. Spring `@Async`: proxy, executor, and real errors

### 6.1. When does `@Async` take effect?

In Spring Boot, `@EnableAsync` activates async interception. A public Spring bean method called **through a Spring proxy** can be submitted to an executor:

```text
JUnit / Controller
      |
      v
Injected Spring bean proxy
      |
      v
@Async("demoExecutor")
      |
      +--- returns CompletableFuture<T> to caller
      |
      v
TaskExecutor worker thread
      |
      +--- perform business operation
      +--- return CompletableFuture.completedFuture(value)
      |    or throw IllegalStateException
      |
      +--- proxy future complete normally/exceptionally
```

If calling `this.asyncMethod()` inside the same bean when using Spring AOP proxy mode, the call usually **bypasses the proxy** and is not dispatched asynchronously. Similarly, `new AsyncGateway()` receives no Spring interception. Tests must inject the bean from the context and call through that bean or another bean.

### 6.2. Prefer returning Future/CompletableFuture over `void` when callers need errors

According to the Spring Framework documentation, an `@Async` method with return type `Future` (or `CompletableFuture`) can propagate errors via the future. With **`@Async void`**, exceptions cannot be sent back through a return value; Spring uses `AsyncUncaughtExceptionHandler` to log/handle exceptions, which typically defaults to logging.

```java
@Async("demoExecutor")
public void fireAndForget() {
    throw new IllegalStateException("async-void-failed");
}
```

This is a snippet inside a Spring bean, **not** a standalone class. A test that merely calls `bean.fireAndForget()` and finishes **has no future to await**. If the contract requires error detection, change the API to `CompletableFuture<Void>` or pass a properly synchronized event/result sink; if `void` is mandatory, register an `AsyncUncaughtExceptionHandler` with a test sink and wait on the sink via latch/future rather than relying on stdout logs.

### 6.3. Avoid accidentally using an uncontrolled executor

- Define an executor bean with a clear name and call `@Async("demoExecutor")`.
- Configure core/max pool size, queue capacity, thread name, rejection, and shutdown policies appropriate for the environment.
- Do not indiscriminately use unbounded queues/pools in production.
- If the executor is saturated, submission/rejection errors may appear **immediately at the call site** or through the future depending on version/setup. Tests must verify the real contract and log queue metrics.
- `thenApplyAsync` without an executor argument can use the default/common pool instead of Spring's `demoExecutor`. If the same executor is needed, pass the explicit `Executor` to the async stage.
- When the context closes, clean up the executor/threads; do not leave non-terminating threads that hang the Maven test runner.

### 6.4. Context does not automatically propagate across threads

Spring transactions are typically thread-bound; `@Async` runs on another thread and therefore **does not automatically inherit the caller's transaction**. `SecurityContext`, MDC/tracing, `RequestContext`, and other ThreadLocals are also not guaranteed automatically. When needed, use official propagation mechanisms (`TaskDecorator`, security-aware executor, explicit context), or pass business IDs into the method. Do not rely on a same-thread test to draw conclusions about production thread pool behavior.

A common mistake is writing an `@Transactional` test, calling an async write, and expecting test rollback to delete all worker DB rows. There is no such guarantee when the other thread uses a separate transaction. Test DB isolation/cleanup properly.

### 6.5. `@Scheduled` and callback errors

`@Scheduled` methods normally do not return a `CompletableFuture` to a JUnit test; exceptions from repeating scheduled tasks may be **logged and suppressed** by the scheduler error handler, allowing subsequent runs to continue. Test the job's business service/future directly; use a fake clock/controlled trigger or an in-memory scheduler when schedule testing is needed, rather than waiting for real cron ticks. With fixed-rate/fixed-delay, verify failure recovery and do not treat a logged error as a passing test.

## 7. Complete Java 17 + Spring Boot 3.5 + JUnit Jupiter example

The example features a **real Spring async proxy** and **CompletionStage unit tests**:

- `AsyncGateway` runs `@Async("demoExecutor")`, returning `CompletableFuture<String>`; covers success, throw, and latch wait cases.
- `OrderWorkflow` injects `AsyncGateway` from the container and builds callbacks using `thenApply`/`whenComplete`/`exceptionally`/`handle`.
- `AsyncWorkflowIntegrationTest` tests the Spring proxy, worker errors, callback errors, recovery, wait timeouts, and awaited callback assertions.
- `CompletableFutureUnitTest` tests pure Java rules without Spring: composition, exception wrapping, observer exceptions, recovery, `allOf`, timeout, and cancellation.
- No external database or network; both test classes run with `mvn test`.

### 7.1. Directory tree

```text
async-callback-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/asyncdemo/
    │   ├── AsyncDemoApplication.java
    │   ├── AsyncGateway.java
    │   └── OrderWorkflow.java
    └── test/java/com/example/asyncdemo/
        ├── AsyncWorkflowIntegrationTest.java
        └── CompletableFutureUnitTest.java
```

### 7.2. Maven POM

File **`pom.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>async-callback-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
```

`spring-boot-starter` provides the core Spring context/AOP infrastructure for `@EnableAsync`; `spring-boot-starter-test` provides JUnit Jupiter and assertion dependencies. Spring Web, databases, or Testcontainers are unnecessary. In other projects using Spring Boot 4/Spring Framework 7, check the corresponding modules/test libraries; this example pins **Boot 3.5.0 + Java 17**.

### 7.3. Spring Boot application + executor bean

File **`src/main/java/com/example/asyncdemo/AsyncDemoApplication.java`**:

```java
package com.example.asyncdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@SpringBootApplication
@EnableAsync
public class AsyncDemoApplication {

    @Bean("demoExecutor")
    ThreadPoolTaskExecutor demoExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("demo-async-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);
        return executor;
    }

    public static void main(String[] args) {
        SpringApplication.run(AsyncDemoApplication.class, args);
    }
}
```

Spring manages the lifecycle of the `ThreadPoolTaskExecutor` bean (initialization and destruction). `@Async("demoExecutor")` on other beans explicitly selects this pool, avoiding dependence on the default executor. For production, choose queue/pool/shutdown policies based on throughput/retry SLAs; for this test, up to two workers suffice.

### 7.4. AsyncGateway: success, exception, and gate methods

File **`src/main/java/com/example/asyncdemo/AsyncGateway.java`**:

```java
package com.example.asyncdemo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncGateway {

    @Async("demoExecutor")
    public CompletableFuture<String> authorize(
            String orderId, boolean fail) {

        if (fail) {
            throw new IllegalStateException(
                    "gateway-unavailable:" + orderId);
        }

        return CompletableFuture.completedFuture(
                "auth-" + orderId);
    }

    @Async("demoExecutor")
    public CompletableFuture<String> awaitGate(
            CountDownLatch started,
            CountDownLatch release) {

        started.countDown();

        try {
            if (!release.await(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException("gate-timeout");
            }
            return CompletableFuture.completedFuture("released");
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "worker-interrupted", interrupted);
        }
    }
}
```

Why does `authorize` return `completedFuture` inside the worker? Spring `@Async` supports methods returning `Future`/`CompletableFuture` so the proxy can dispatch execution to the executor; the method body can create a `completedFuture` on the worker, while the **caller-side proxy future** completes after the worker finishes or throws. Throwing `IllegalStateException` inside the worker is delivered to the caller's future, rather than jumping onto the test's stack frame before `get` is called.

The `awaitGate` method is for demo purposes only; a latch blocking the worker for 30 seconds is a hang-prevention bound. **Do not use a latch like this in production business services.** The test always releases the gate in `finally`.

### 7.5. OrderWorkflow: callbacks with different behaviors

File **`src/main/java/com/example/asyncdemo/OrderWorkflow.java`**:

```java
package com.example.asyncdemo;

import java.util.concurrent.CompletableFuture;

import org.springframework.stereotype.Service;

@Service
public class OrderWorkflow {

    private final AsyncGateway gateway;

    public OrderWorkflow(AsyncGateway gateway) {
        this.gateway = gateway;
    }

    public CompletableFuture<String> submit(
            String orderId, boolean fail) {
        return gateway.authorize(orderId, fail)
                .thenApply(value -> "READY:" + value);
    }

    public CompletableFuture<String> callbackFails(
            String orderId) {
        return gateway.authorize(orderId, false)
                .thenApply(value -> {
                    throw new IllegalArgumentException(
                            "callback-invalid:" + orderId);
                });
    }

    public CompletableFuture<String> observerFails(
            String orderId) {
        return gateway.authorize(orderId, false)
                .whenComplete((value, error) -> {
                    if (error == null) {
                        throw new IllegalArgumentException(
                                "observer-invalid:" + orderId);
                    }
                });
    }

    public CompletableFuture<String> recover(
            String orderId) {
        return gateway.authorize(orderId, true)
                .exceptionally(error -> "FALLBACK:" + orderId);
    }

    public CompletableFuture<String> classify(
            String orderId, boolean fail) {
        return gateway.authorize(orderId, fail)
                .handle((value, error) ->
                        error == null
                                ? "READY:" + value
                                : "FAILED:" + orderId);
    }
}
```

Because Spring injects an **AsyncGateway proxy** into `OrderWorkflow`, calling `gateway.authorize` is not self-invocation. It genuinely runs on the executor. The five methods return **the exact dependent stage**, so the caller/JUnit can observe:

- `submit`: worker fails → returned stage fails.
- `callbackFails`: worker succeeds but `thenApply` throws → returned stage fails.
- `observerFails`: worker succeeds, `whenComplete` throws → returned stage fails.
- `recover`: worker fails → `exceptionally` resolves to fallback value.
- `classify`: `handle` converts both success/failure into result strings per demo policy.

If `OrderWorkflow.submit` instead called `gateway.authorize(...).thenApply(...)` yet **returned the future from `gateway.authorize` instead of the future from `thenApply`**, mapping callback errors would be abandoned. This is a key reason to return the **final stage containing all callback assertions/transformations**.

### 7.6. JUnit integration: testing real `@Async`, 9 methods

File **`src/test/java/com/example/asyncdemo/AsyncWorkflowIntegrationTest.java`**:

```java
package com.example.asyncdemo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class AsyncWorkflowIntegrationTest {

    @Autowired
    private AsyncGateway gateway;

    @Autowired
    private OrderWorkflow workflow;

    @Test
    void asyncSuccessIsAwaitedAndReturned() throws Exception {
        String value = workflow.submit("A1", false)
                .get(5, TimeUnit.SECONDS);

        assertEquals("READY:auth-A1", value);
    }

    @Test
    void exceptionFromAsyncWorkerIsDeliveredByGet() {
        ExecutionException failure = assertThrows(
                ExecutionException.class,
                () -> workflow.submit("A2", true)
                        .get(5, TimeUnit.SECONDS));

        assertInstanceOf(
                IllegalStateException.class, failure.getCause());
        assertEquals(
                "gateway-unavailable:A2",
                failure.getCause().getMessage());
    }

    @Test
    void exceptionFromAsyncWorkerIsWrappedByJoin() {
        CompletionException failure = assertThrows(
                CompletionException.class,
                () -> workflow.submit("A3", true)
                        .orTimeout(5, TimeUnit.SECONDS).join());

        assertInstanceOf(
                IllegalStateException.class, failure.getCause());
    }

    @Test
    void exceptionThrownInsideThenApplyReachesJUnit() {
        ExecutionException failure = assertThrows(
                ExecutionException.class,
                () -> workflow.callbackFails("A4")
                        .get(5, TimeUnit.SECONDS));

        assertInstanceOf(
                IllegalArgumentException.class, failure.getCause());
        assertEquals(
                "callback-invalid:A4",
                failure.getCause().getMessage());
    }

    @Test
    void exceptionThrownInsideWhenCompleteReachesJUnit() {
        ExecutionException failure = assertThrows(
                ExecutionException.class,
                () -> workflow.observerFails("A5")
                        .get(5, TimeUnit.SECONDS));

        assertInstanceOf(
                IllegalArgumentException.class, failure.getCause());
    }

    @Test
    void exceptionallyReturnsFallbackButHidesUpstreamFailure()
            throws Exception {
        CompletableFuture<String> result = workflow.recover("A6");

        assertEquals(
                "FALLBACK:A6", result.get(5, TimeUnit.SECONDS));
        assertFalse(result.isCompletedExceptionally());
    }

    @Test
    void handleCanClassifySuccessAndFailure() throws Exception {
        assertEquals(
                "READY:auth-A7",
                workflow.classify("A7", false)
                        .get(5, TimeUnit.SECONDS));
        assertEquals(
                "FAILED:A7",
                workflow.classify("A7", true)
                        .get(5, TimeUnit.SECONDS));
    }

    @Test
    void assertionInThenAcceptMustBeAwaited() throws Exception {
        CompletableFuture<Void> checked =
                gateway.authorize("A8", false)
                        .thenAccept(value ->
                                assertEquals("auth-A8", value));

        // Await the stage of thenAccept, not just the source future.
        checked.get(5, TimeUnit.SECONDS);
    }

    @Test
    void getTimeoutDoesNotCancelBlockedWorker() throws Exception {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CompletableFuture<String> running =
                gateway.awaitGate(started, release);

        try {
            assertTrue(started.await(5, TimeUnit.SECONDS));
            assertThrows(
                    TimeoutException.class,
                    () -> running.get(80, TimeUnit.MILLISECONDS));
            assertFalse(running.isDone());
        } finally {
            release.countDown();
        }

        assertEquals(
                "released", running.get(5, TimeUnit.SECONDS));
    }
}
```

**Test #9 has two different timeout layers**: `started.await(5s)` ensures the worker has started running, `running.get(80ms)` expects a timeout because the worker is waiting for release, and then `release.countDown()` in `finally` lets the worker finish. Asserting `get(5s) == "released"` proves that **a wait timeout does not mean the computation was cancelled**.

**Test #3 uses `orTimeout(5s)`** to avoid `join` hanging indefinitely. If the worker deadlocks, the cause will be `TimeoutException` instead of `IllegalStateException`; the cause assertion fails, detecting the bug rather than producing a false pass.

### 7.7. Unit JUnit: 11 methods of Java 17 CompletableFuture

File **`src/test/java/com/example/asyncdemo/CompletableFutureUnitTest.java`**:

```java
package com.example.asyncdemo;

import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CompletableFutureUnitTest {

    @Test
    void thenApplyAndThenComposeProduceValue() {
        CompletableFuture<Integer> value =
                CompletableFuture.completedFuture("10")
                        .thenApply(Integer::parseInt)
                        .thenCompose(number ->
                                CompletableFuture.completedFuture(
                                        number * 2));

        assertEquals(20, value.join());
    }

    @Test
    void thenCombineWaitsForBothValues() {
        CompletableFuture<String> combined =
                CompletableFuture.completedFuture("A")
                        .thenCombine(
                                CompletableFuture.completedFuture("B"),
                                (a, b) -> a + b);

        assertEquals("AB", combined.join());
    }

    @Test
    void thenApplyExceptionBelongsToReturnedStage() {
        CompletableFuture<String> source =
                CompletableFuture.completedFuture("OK");

        CompletableFuture<String> derived =
                source.thenApply(value -> {
                    throw new IllegalArgumentException("bad-callback");
                });

        assertEquals("OK", source.join());

        CompletionException failure = assertThrows(
                CompletionException.class, derived::join);
        assertInstanceOf(
                IllegalArgumentException.class, failure.getCause());
    }

    @Test
    void whenCompleteFailureDoesNotChangeOriginalStage() {
        CompletableFuture<String> source =
                CompletableFuture.completedFuture("OK");

        CompletableFuture<String> observed =
                source.whenComplete((value, error) -> {
                    throw new IllegalStateException("observer-error");
                });

        assertEquals("OK", source.join());

        CompletionException failure = assertThrows(
                CompletionException.class, observed::join);
        assertInstanceOf(
                IllegalStateException.class, failure.getCause());
    }

    @Test
    void exceptionallyConvertsFailureToFallback() {
        CompletableFuture<String> source =
                CompletableFuture.failedFuture(
                        new IllegalStateException("failed"));

        CompletableFuture<String> recovered =
                source.exceptionally(error -> "FALLBACK");

        assertEquals("FALLBACK", recovered.join());
        assertTrue(source.isCompletedExceptionally());
        assertFalse(recovered.isCompletedExceptionally());
    }

    @Test
    void handleProcessesSuccessAndFailure() {
        CompletableFuture<String> success =
                CompletableFuture.completedFuture("VALUE")
                        .handle((value, error) ->
                                error == null ? value : "ERROR");

        CompletableFuture<String> failed =
                CompletableFuture.<String>failedFuture(
                        new IllegalStateException("failed"))
                        .handle((value, error) ->
                                error == null ? value : "ERROR");

        assertEquals("VALUE", success.join());
        assertEquals("ERROR", failed.join());
    }

    @Test
    void allOfPropagatesAFailedBranch() {
        CompletableFuture<String> first =
                CompletableFuture.completedFuture("OK");
        CompletableFuture<String> second =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("bad"));

        CompletionException failure = assertThrows(
                CompletionException.class,
                () -> CompletableFuture.allOf(first, second).join());

        assertInstanceOf(
                IllegalArgumentException.class, failure.getCause());
    }

    @Test
    void failingAssertionInCallbackIsObservable() {
        CompletableFuture<Void> checked =
                CompletableFuture.completedFuture("actual")
                        .thenAccept(value ->
                                assertEquals("expected", value));

        CompletionException failure = assertThrows(
                CompletionException.class, checked::join);

        assertInstanceOf(AssertionError.class, failure.getCause());
    }

    @Test
    void orTimeoutFailsPendingFuture() {
        CompletableFuture<String> pending = new CompletableFuture<>();
        pending.orTimeout(30, TimeUnit.MILLISECONDS);

        ExecutionException failure = assertThrows(
                ExecutionException.class,
                () -> pending.get(5, TimeUnit.SECONDS));

        assertInstanceOf(
                TimeoutException.class, failure.getCause());
        assertTrue(pending.isCompletedExceptionally());
    }

    @Test
    void completeOnTimeoutReturnsFallback() throws Exception {
        CompletableFuture<String> pending = new CompletableFuture<>();
        pending.completeOnTimeout(
                "DEFAULT", 30, TimeUnit.MILLISECONDS);

        assertEquals(
                "DEFAULT", pending.get(5, TimeUnit.SECONDS));
        assertFalse(pending.isCompletedExceptionally());
    }

    @Test
    void cancelCompletesFutureExceptionally() {
        CompletableFuture<String> pending = new CompletableFuture<>();

        assertTrue(pending.cancel(true));
        assertTrue(pending.isCancelled());
        assertTrue(pending.isCompletedExceptionally());
        assertThrows(
                CancellationException.class, pending::join);
    }
}
```

**JUnit test count:** integration class **9**, unit class **11**, total **20 `@Test`**. Unit tests use `completedFuture`/`failedFuture` and create no threads or touch the network. Timeout cases in the unit class use `CompletableFuture`'s timer (30ms) with a wait deadline of up to 5 seconds; negative assertions use `assertThrows`, so they succeed when the expected error is observed, rather than being broken tests.

### 7.8. Running Maven and expected results

From the directory containing `pom.xml`, requiring JDK 17+ and Maven:

```bash
mvn test
```

Run a single test class:

```bash
mvn -Dtest=CompletableFutureUnitTest test
mvn -Dtest=AsyncWorkflowIntegrationTest test
```

If Maven Wrapper has already been generated: `./mvnw test` (Linux/macOS) or `mvnw.cmd test` (Windows).

Expected in a suitable environment: **20 test methods run, 0 failures, 0 errors**. When a callback assertion is intentionally designed to fail in `failingAssertionInCallbackIsObservable`, the test method still **PASSES** because it verifies a `CompletionException` with cause `AssertionError`. An unobserved future with an error is not sufficient evidence to let a test PASS.

The illustrative code has been reviewed for imports, APIs, and exception semantics against Java 17/Spring Boot 3.5, **not claimed to have run Maven during authoring**. When integrating into a real project, run the tests on your JDK/CI and adjust executor/timeouts to match your environment.

## 8. Test errors that get hidden or tested at the wrong layer

### 8.1. Catching an exception and ignoring it

```java
return gateway.authorize(orderId, true)
        .exceptionally(error -> {
            log.warn("Async failed", error);
            return "OK";
        });
```

This snippet assumes `gateway` and `log` exist; it is not standalone. If the business contract requires propagating the failure, returning `"OK"` **hides the error**. When a test only checks the `"OK"` result, it can produce a false positive even though the operation failed. Decide explicitly between recovery and failure propagation, and check metrics/audit and downstream side effects too.

### 8.2. Callback has an assertion but its stage is not returned/awaited

```java
CompletableFuture<String> original = service.loadAsync();

original.thenAccept(value ->
        assertEquals("expected", value));

original.get(5, TimeUnit.SECONDS); // WRONG: only waits for ORIGINAL
```

This is an anti-pattern; `service` is hypothetical. If `thenAccept` throws an error, `original` can still succeed. The right way is:

```java
CompletableFuture<Void> checked =
        original.thenAccept(value ->
                assertEquals("expected", value));
checked.get(5, TimeUnit.SECONDS);
```

### 8.3. Callback fails but test only asserts `isDone()`

`isDone()` is true for normal, exceptional, and cancelled completions. Replace with `get(timeout)`, `join`, or assert both state and cause. If the test covers the entire pipeline, await the **terminal stage**, not just the upstream source.

### 8.4. Using `@Async void` and expecting the test to receive the exception

`@Async void` has no `Future` for the caller to receive errors. Use `CompletableFuture<Void>` when the contract needs success/failure visibility, or configure an `AsyncUncaughtExceptionHandler` with a synchronized test sink instead of relying on logs. Avoid fire-and-forget for logic requiring transactional integrity or important delivery guarantees without queues/retries/monitoring.

### 8.5. Calling self-invocation and assuming the method runs on the pool

`this.doAsync()` within the same bean bypasses proxy-based Spring `@Async`. The method can execute **synchronously**, causing tests to sometimes pass because assertions run immediately, while production calls through the proxy run asynchronously and fail. Extract to another bean or call through the proper proxy; integration tests should verify thread/latch at key boundaries.

### 8.6. Waiting in the test with `Thread.sleep(1000)`

When CI is slow, 1 second is not enough; when the machine is fast, 1 second is wasted. Use `CompletableFuture.get(timeout)`, `CountDownLatch`, a barrier, Awaitility (if installed) with bounded polling, or a test executor/fake scheduler. Clean up the worker in `finally` after a timeout.

### 8.7. Not distinguishing source errors from callback errors

If upstream already failed and `whenComplete` also throws, the returned stage may still retain the **upstream error** per Java semantics. If upstream succeeded but the callback throws, the returned stage carries the callback error. To be certain what failed, test separate cases; do not conclude solely from console error messages.

### 8.8. `allOf` has one failed branch while other branches are still running

`CompletableFuture.allOf(a,b,c)` waits for all to finish; when one fails, the combined future fails. It does not mean the framework rolled back or cancelled every other branch. Use test state isolation, cancellation/compensation as appropriate for the business domain. If async branches perform database writes, partial effects may occur; do not expect an outer test transaction rollback to cover them automatically.

### 8.9. Running a callback on a different executor from the registered one

`thenApply` may run on the thread completing the upstream stage or the registering thread if the source is already done; do not assert "the callback always runs on pool-1-thread-1". Use `thenApplyAsync` with an explicit executor when thread affinity matters. For ThreadLocal request/security/transaction contexts, test propagation separately.

### 8.10. Timeouts do not automatically roll back external work

`get(timeout)` is only the caller's wait timeout. `orTimeout`/`cancel` changes the future's state but is not guaranteed to stop underlying I/O or jobs. If a timeout triggers a retry, the backend may process the old command in parallel with the new one. Use an **idempotency key** and reconciliation for side effects like payments or message publishing, rather than inferring from a future timeout that the operation did not happen.

## 9. Spring scheduling and bringing errors back to tests

Spring `@Scheduled` can trigger background jobs by `fixedDelay`, `fixedRate`, or `cron`. The "scheduling" topic relates directly to the same problem: **errors happen outside the JUnit test method**.

A recommended structure:

```text
Scheduler (only decides when to trigger)
       |
       v
Job adapter (records correlation ID, metrics, error log)
       |
       v
BusinessWorker.runOneCycle(): CompletableFuture<Result>
       |
       +-- thenApply/thenCompose/handle
       +-- outcome / error / retry decision
       |
       v
Test calls business worker directly
       |
       +-- await CompletableFuture.get(timeout)
       +-- assert result/error/callback
```

With `@Scheduled void`, the JUnit caller has no returned future. Do not test cron by calling `Thread.sleep(60_000)` and checking logs. Instead:

1. **Separate the logic** of running one cycle into a service receiving dependencies/time source.
2. **Unit/integration test** that logic via a Future-returning method or a clear synchronous method.
3. **Test the scheduling adapter** separately to ensure the annotation/config actually triggers on schedule, using a fake clock/scheduler/triggers when appropriate.
4. When a scheduled job fails, observe metrics/error handler/outbox or a bounded sink; do not treat "no exception seen on test thread" as a PASS.
5. For idempotent or overlapping jobs, test concurrent invocations, uniqueness locks, and eventual consistency.
6. When a task is cancelled/interrupted, preserve the interrupt flag and clean up external resources.

Errors in repeating scheduled tasks are typically logged and handled by the scheduler error handler so the schedule continues; therefore **do not assume exceptions will fly into the JUnit thread**. For critical business jobs, provide a dedicated callback/sink reflecting success/failure status and alerts.

## 10. Test matrix table to use in projects

| Case | Setup | Evidence/expected |
|---|---|---|
| Async happy path | Worker returns success | Await terminal stage, assert value |
| Worker throws | `@Async` throws unchecked exception | `get(timeout)` throws `ExecutionException` with right cause |
| Callback transform throws | Upstream succeeds, `thenApply` throws | Returned dependent stage fails, source may still succeed |
| Observer throws | `whenComplete` throws | Returned observed stage fails, do not discard stage |
| Callback assertion fails | `thenAccept` asserts wrong value | Await returned `CompletableFuture<Void>`, JUnit sees `AssertionError` cause |
| Intentional recovery | `exceptionally` returns fallback | Terminal stage succeeds, upstream error is still recorded |
| Classify both outcomes | `handle` with success/error | Assert both branches |
| Multiple futures | `thenCombine`/`allOf` | No error lost in any branch |
| Slow/blocking worker | Latch blocks worker | `get(timeout)` times out, release then `get` succeeds |
| Future cancellation | `cancel(true)` | Future cancelled; do not claim worker was interrupted |
| Executor saturation | Full queue / rejection | Submission error observed per contract, clean up pool |
| `@Async void` | Method throws | Handler/sink receives error, test does not rely on returned future |
| Scheduled job throws | Trigger job via fake scheduler | Error handler/event sink receives error |
| Caller transaction rollback | Worker writes DB on another thread | Read committed state at right boundary, clean up by test ID |
| Concurrent callbacks | Race two completions | Only one outcome wins, invariant not violated |
| Timeout then retry | Underlying side effect may still run | Idempotency / duplicate suppression, no double-write |

## 11. Checklist before marking an async test QA PASS

- [ ] The test **awaits the terminal future/stage** containing all callbacks to verify.
- [ ] `get(timeout)` is used at test boundaries instead of waiting indefinitely.
- [ ] When a future fails, the test checks the **actual cause**, not just `isDone()`.
- [ ] I distinguish `ExecutionException`, `CompletionException`, `CancellationException`, and `TimeoutException`.
- [ ] Assertions inside `thenAccept`/`whenComplete` are not abandoned.
- [ ] `whenComplete` only observes; `exceptionally` and `handle` can turn failure into success.
- [ ] The test knows which callbacks run on upstream success vs failure.
- [ ] I do not assume `thenApply` always runs on a separate executor.
- [ ] `thenApplyAsync` passes an explicit executor when thread/Context control is needed.
- [ ] `@Async` is invoked through a Spring bean proxy, not via `new` or self-invocation.
- [ ] Executor size/queue/shutdown/rejection match test and production needs.
- [ ] `Thread.sleep` is not used as a way to wait for work to finish.
- [ ] For timeout tests, a latch/barrier is used and released in `finally`.
- [ ] I understand `get(timeout)` does not auto-cancel computation, and `cancel(true)` does not guarantee interruption.
- [ ] `@Async void` has a dedicated handler/sink or is replaced with `CompletableFuture<Void>` when error propagation is needed.
- [ ] `@Scheduled` is tested by cycle logic and error signaling, not by sleeping for cron.
- [ ] ThreadLocal transaction/security/MDC are handled per executor/context.
- [ ] Async DB writes have their own fixture cleanup; do not assume test rollback covers worker threads.
- [ ] Negative tests exist for worker throw, callback throw, and explicit recovery.
- [ ] Ran `mvn test` on JDK 17+ and no background task leaks affect the suite.
- [ ] Do not infer from a passing test that retries, compensation, or external system side effects finished.

**Conclusion:** To test asynchronously reliably, **return the right completion stage, await the final stage with a deadline, verify exception causes, and use deterministic coordination** instead of sleep. A callback throwing an error will not automatically appear in JUnit if abandoned; `@Async void` and `@Scheduled` require dedicated error reporting/sinks even more. **Proper testing is not merely "the method was called", but "the entire pipeline completed with a verified outcome".**

### Official documentation

- [Java 17 — CompletableFuture Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java 17 — CompletionStage Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [Spring Framework — Task Execution and Scheduling, @Async exceptions](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — @Async Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [JUnit Jupiter — Assertions and Timeouts](https://docs.junit.org/5.11.3/user-guide/index.html)