# Exceptions Handled by the Executor in Spring Application Events

## 1. Real-World Problem: Publisher Succeeds Yet the Listener Errored

When processing Spring Application Events asynchronously, a symptom that easily misleads operators is:

- Code calling `applicationEventPublisher.publishEvent(event)` completes **without receiving an exception**.
- An `@EventListener` threw an `IllegalStateException` or an external-service access error.
- The error log appears on an executor thread, not the request-handling thread.
- The HTTP status or publisher return still looks successful.
- Other listeners still run; some post-processing work is missing.

This may be **expected behavior for exception propagation across thread boundaries**, rather than Spring "swallowing" errors.

For example: a user places an order, `OrderPlaced` is published, and an email-sending listener runs in an executor. If the email listener throws an exception **after the task has been accepted by the executor**, the thread calling publish generally cannot catch that error with a `try/catch` around `publishEvent`. Errors must be observed at the **task/listener/executor boundary** via `ErrorHandler`, `Future`, `AsyncUncaughtExceptionHandler`, or appropriate monitoring.

**Distinguish first:** "Exception handled by the executor" can mean one of several failure paths. Determine whether **the error occurred at task submission**, **inside the running listener**, **inside a wrapper/decorator**, or **after a Future completed exceptionally**.

> **Core conclusion:** the publisher not throwing an exception does not prove the listener succeeded. Conversely, a listener exception does not always mean the publisher's transaction rolled back. You must identify the exact dispatch mechanism, handler, and transaction boundary.

## 2. Diagram of the Two Event Processing Paths

### 2.1. Default: Synchronous on the Publishing Thread

In Spring Framework, `SimpleApplicationEventMulticaster` processes listeners on the calling thread by default:

```text
HTTP/request thread
  |
  +-- OrderService.placeOrder(...)
       |
       +-- publishEvent(OrderPlaced)
            |
            +-- Listener A executes immediately
                 |
                 +-- throws IllegalStateException
                      |
                      v
             exception propagates to publishEvent
            |
            X  Subsequent listeners may not be called
```

If the multicaster has **no `ErrorHandler` configured** and a synchronous listener throws an unchecked exception, the publisher normally sees the exception and the publish call is interrupted.

### 2.2. With an Executor: Listeners Are Submitted as Tasks

```text
Publisher thread                      Worker thread
----------------                      ----------------
publishEvent(OrderPlaced)
  |
  +-- executor.execute(task A) ------> listener A
  |                                       |
  |                                       +-- throws
  |                                             |
  |                                             +--> multicaster ErrorHandler?
  |                                             |       |
  |                                             |       +--> log/suppress/rethrow
  |                                             |
  |                                             +--> executor/UncaughtExceptionHandler
  |                                                  if error continues escaping task
  |
  +-- executor.execute(task B) ------> listener B
  |
  +-- publishEvent returns
```

Successful submission usually only indicates **the executor accepted the task**; it is not an acknowledgement that the listener finished. For errors occurring later on the worker, a `try/catch` on the publisher thread cannot reach backward across threads.

**Ordering warning:** the executor may run task A before, during, or after the publisher continues. Never write tests relying on a fixed log order without a latch or synchronization condition.

## 3. Identifying Which Layer the Error Happened In

| Where it occurs | Example | Who can observe it directly? | Diagnostic tool |
| --- | --- | --- | --- |
| **Publisher before dispatch** | Validation in service throws | Publisher thread | Caller's `try/catch`, transaction tests |
| **Executor rejects submission** | Queue full, executor shut down | Thread calling `execute/submit`, barring custom fallback/rejection | `RejectedExecutionException`/`TaskRejectedException`, queue metrics |
| **Inside synchronous listener** | `@EventListener` throws | Usually publisher unless suppressed | Stack trace from `publishEvent`, multicaster `ErrorHandler` |
| **Inside executor-run listener** | External service times out after task accepted | Worker/executor or `ErrorHandler` on task | Error handler, logs, async probes |
| **Inside `@Async void`** | Async-intercepted listener throws | `@Async`'s `AsyncUncaughtExceptionHandler` | Annotation-driven async handler |
| **Inside `Future/CompletableFuture`** | Task completes exceptionally | Caller reading Future or completion callback | `get()`, `join()`, `whenComplete` |
| **Inside `TaskDecorator`/task wrapper** | Context restoration fails | Wrapper/executor boundary | Decorator logging, task instrumentation |
| **After commit / other transport** | Broker relay fails | Separate relay/consumer | Outbox, retries, dead-letter monitoring |

Do not lump all of these together as "the executor caught the error". A `FutureTask` can **store the exception waiting for `Future.get()`**; an `ErrorHandler` can **log and suppress**; a `Thread.UncaughtExceptionHandler` may only see **uncaught** errors escaping the thread. Those three cases produce very different outcomes.

## 4. Configuration That Actually Determines the Exception Path

Default behavior of Spring Application Events:

- No dedicated task executor configured: `SimpleApplicationEventMulticaster` invokes listeners synchronously.
- Executor assigned to the multicaster: listeners supporting async execution are submitted via `Executor.execute(...)`.
- Depending on `ApplicationListener.supportsAsyncExecution()`, some listeners are not permitted to run asynchronously via the multicaster and still execute on the publisher thread, such as transaction-synchronized listeners.
- `SimpleApplicationEventMulticaster.setErrorHandler(...)` defines the policy for handling **errors thrown by listeners**.
- `@Async` is a **separate** AOP/annotation-driven async mechanism, not identical to assigning an executor to the multicaster.
- A custom multicaster may implement different logic; do not guess from thread names without knowing the implementation.

### 4.1. Spring Context Configuration

When wanting regular listeners to use an executor:

```java
@Configuration(proxyBeanMethods = false)
class EventConfiguration {

    @Bean(name = "applicationEventMulticaster")
    SimpleApplicationEventMulticaster applicationEventMulticaster(
            @Qualifier("eventExecutor") ThreadPoolTaskExecutor executor) {

        var multicaster = new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(executor);
        multicaster.setErrorHandler(error -> {
            // Log real exception, increment metrics, and enforce error policy.
            logger.error("Application event listener failed", error);
        });
        return multicaster;
    }

    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("domain-event-");
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.initialize();
        return executor;
    }
}
```

This is **illustrative configuration**: requires imports for Spring annotations, `SimpleApplicationEventMulticaster`, `ThreadPoolTaskExecutor`, and a logger defined in the class. It is not section 8's standalone runnable project. In a real project, let Spring manage the executor bean lifecycle rather than manually shutting down an executor with active tasks.

Declaring a bean named **`applicationEventMulticaster`** is how the Spring context recognizes a custom multicaster. Creating an arbitrary `ThreadPoolTaskExecutor` bean alone is not enough to ensure all event listeners run on that executor.

### 4.2. Note on Listeners Not Supporting Async

Since Spring Framework 6.1, `ApplicationListener.supportsAsyncExecution()` indicates whether a listener can be invoked asynchronously by the multicaster. `TransactionalApplicationListener` implementations are not suitable for direct async dispatch by the multicaster in order to preserve transaction synchronization.

Thus, **the same multicaster with an executor** can still execute some listeners on the publisher thread. Errors from that group can propagate to the publisher if the handler rethrows or is unconfigured, unlike errors in tasks running on the pool.

Never claim "simply calling `setTaskExecutor` makes every `@TransactionalEventListener` run on a worker thread".

## 5. The Multicaster's ErrorHandler: Most Important Observation Point

`org.springframework.util.ErrorHandler` is an interface with the method:

```java
void handleError(Throwable t);
```

`SimpleApplicationEventMulticaster.setErrorHandler(...)` invokes this handler when **a listener throws a `Throwable`**. General flow:

```text
invokeListener(listener, event)
   |
   +-- try: invoke listener
   |
   +-- catch Throwable:
          |
          +-- ErrorHandler.handleError(error)
                 |
                 +-- handler returns normally
                 |      -> listener error is suppressed here
                 |
                 +-- handler rethrows exception
                        -> error escapes task or publisher thread,
                           depending on actual dispatch
```

With a handler that merely logs and returns, the publisher typically receives no exception, and the worker task finishes **from the executor's perspective** with no thrown error. That **does not retry the failed operation**; it only changes how the error is reported outward.

### 5.1. LOG_AND_SUPPRESS vs. LOG_AND_PROPAGATE

Spring provides `TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER` and `TaskUtils.LOG_AND_PROPAGATE_ERROR_HANDLER` in `org.springframework.scheduling.support`. They represent two common policies:

| Policy | Action | Consequence |
| --- | --- | --- |
| **Log + suppress** | Logs error; does not rethrow | Task may be treated as completed normally; monitors watching only uncaught exceptions may miss it |
| **Log + propagate** | Logs error; rethrows | For sync, caller may receive error; for async, exception continues to executor/task boundary |
| **Custom handler** | Log/metric/alert/record status, may or may not rethrow | Must clearly define handling and ensure side-effect idempotency |
| **No handler** | Does not intercept exception at multicaster | Sync may propagate to publisher; async escapes to worker/task per executor |

`ErrorHandler` implementations can receive `Error` as well as `Exception`. Do not casually suppress severe JVM errors like `OutOfMemoryError`; custom error policies must distinguish recoverable errors from those unsafe to continue after.

### 5.2. One ErrorHandler Shared Across Multiple Listeners

Example:

```java
multicaster.setErrorHandler(error -> {
    failureCounter.incrementAndGet();
    logger.error("Event listener failure", error);
});
```

This is an **illustrative snippet**, requiring `multicaster`, `failureCounter`, and `logger` defined in the application. The handler receives a `Throwable` yet **does not automatically know which event ID, listener method, or tenant** failed. When metadata is needed, you can:

- Put event ID/correlation ID into logging/tracing context properly.
- Wrap business listeners in an adapter carrying operation name and event metadata.
- Record failures in monitoring with low-cardinality tags; avoid raw `orderId`/`userId` as metric labels.
- Do not rely solely on exception messages for classification: use exception types, error codes, and validated context.

**Do not log full event payloads** if they contain PII, tokens, or sensitive data.

## 6. Distinguishing Listener Errors from Executor Task-Rejection Errors

These two cases are often mistakenly grouped under the same `catch`:

### Case A: Task Accepted, Then Errors

```text
publisher
  -> executor.execute(task)  [accepted]
  -> publishEvent returns
worker
  -> listener throws
  -> ErrorHandler/uncaught/future pathway
```

This error normally does not return to the publisher.

### Case B: Task Rejected Before Running

```text
publisher
  -> executor.execute(task)
       -> rejected (saturated/shutdown)
       -> rejection policy or fallback per multicaster implementation
```

Submission errors can occur **right on the publisher thread**. With Spring `ThreadPoolTaskExecutor`, rejection may surface as `org.springframework.core.task.TaskRejectedException` (wrapping/related to `RejectedExecutionException`), depending on API/configuration.

**Subtle point:** do not assert that every `RejectedExecutionException` in the multicaster always propagates straight to the caller. Some `SimpleApplicationEventMulticaster` versions/implementations catch `RejectedExecutionException` on submission and **invoke the listener locally on the publisher thread** as a fallback when the executor is shutting down or inactive. Therefore, when queues fill up or pools shut down, actual behavior depends on **Spring version, executor type, and rejection policy**. Check the implementation in use and test that exact scenario in your application.

If fallback runs the listener synchronously, the listener's exception can once again propagate to the publisher if there is no suppressing `ErrorHandler`. Never assume that merely "having an executor" isolates every error from the caller.

### 6.1. ThreadPoolExecutor Rejection Policies

| RejectedExecutionHandler | Typical Java behavior | Risk when used for events |
| --- | --- | --- |
| `AbortPolicy` | Throws `RejectedExecutionException` | Task is not accepted; how multicaster handles rejection may vary by version |
| `CallerRunsPolicy` | Runs task on caller thread while pool is active; if shut down, usually does not run | Request may suddenly block; context/transaction/timing changes |
| `DiscardPolicy` | Drops task without necessarily throwing | Event processing can be lost while publisher still succeeds |
| `DiscardOldestPolicy` | Drops oldest queued task and retries submitting new one | Can silently drop other critical work, very hard to diagnose |

These are JDK `ThreadPoolExecutor` policies. When configuring through Spring, confirm which policy the executor actually uses and whether wrappers alter behavior.

Do not use `DiscardPolicy` as a default strategy to "avoid errors" on vital business events. **No exception does not mean the task ran.**

### 6.2. Executor Sizing and Backpressure

For `ThreadPoolTaskExecutor`, consider:

- `corePoolSize`: baseline maintained workers.
- `maxPoolSize`: maximum worker limit.
- `queueCapacity`: how many tasks can wait.
- Task duration p95/p99: how long each listener holds a worker.
- Event arrival rate: bursts can fill queues even when average load is low.
- Rejection metrics and shutdown behavior.

Under the standard `ThreadPoolExecutor` model, tasks are queued once core threads are busy; the executor only grows threads toward max when the queue stops accepting tasks. Setting an overly large queue can prevent `maxPoolSize` from ever engaging as imagined and build up huge backlogs.

Choose bounded executors with explicit backpressure when resource control is needed; however, **boundedness does not automatically create retries, delivery guarantees, or a proper error policy**.

## 7. @Async @EventListener Differs from an Executor Configured on the Multicaster

Two common approaches:

### 7.1. Running Async via the Multicaster

```java
multicaster.setTaskExecutor(eventExecutor);
multicaster.setErrorHandler(errorHandler);
```

A regular `@EventListener` is invoked by Spring's multicaster on the task executor if it supports async. When the listener throws, the multicaster's `ErrorHandler` is a direct interception point.

### 7.2. Running Async via @Async Proxy

```java
@Async("eventExecutor")
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    sendNotification(event);
}
```

This is an illustrative method in a Spring bean: requires `@EnableAsync`, an executor bean named `eventExecutor`, `OrderPlaced`, and `sendNotification(...)`.

Here, annotation-driven async uses a **Spring AOP interceptor/proxy**. If it is a `void` `@Async` method throwing after starting on a worker, the appropriate handler is typically the `AsyncUncaughtExceptionHandler` provided by `AsyncConfigurer` or async configuration. This error policy is **not identical** to `SimpleApplicationEventMulticaster.setErrorHandler(...)`.

If you configure **both** a multicaster executor **and** `@Async` on the listener, you introduce an extra submission/task boundary. Exceptions thrown by the `void` async method may be handled by the async interceptor and **never escape back** through the multicaster `ErrorHandler`. So do not treat `setErrorHandler` on the multicaster as a blanket handler for errors from nested async operations.

**Clean design:** choose one clear primary async boundary per listener category, place monitoring right at that boundary, and avoid purposeless double-executor layering.

## 8. Runnable Spring Framework 6.2 + Java 17 Example Without Random Timing

The following example intentionally avoids `Thread.sleep(100)` or guessing from logs. It demonstrates:

1. With a synchronous multicaster, the exception reaches the publisher.
2. With an executor-backed multicaster, the publisher returns **before** the listener is allowed to throw.
3. The `ErrorHandler` records and suppresses the worker error.
4. A second listener still runs, proving one task failing does not necessarily block subsequent tasks.
5. Tests wait via `CountDownLatch` with timeouts rather than assuming OS scheduling.

The project uses **JDK 17+**, Maven, and **Spring Framework 6.2.12**; only `spring-context` is required.

### 8.1. Project Structure

```text
executor-event-failure/
├── pom.xml
└── src/main/java/demo/ExecutorEventFailureDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>executor-event-failure</artifactId>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.ExecutorEventFailureDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/ExecutorEventFailureDemo.java`:

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;

public final class ExecutorEventFailureDemo {

    public static final class OrderEvent extends ApplicationEvent {
        private final String orderId;

        public OrderEvent(String orderId) {
            super(orderId);
            this.orderId = orderId;
        }

        public String orderId() {
            return orderId;
        }
    }

    private static void synchronousExample() {
        var multicast = new SimpleApplicationEventMulticaster();

        multicast.addApplicationListener(
                new ApplicationListener<OrderEvent>() {
                    @Override
                    public void onApplicationEvent(OrderEvent event) {
                        throw new IllegalStateException("sync failure");
                    }
                });

        try {
            multicast.multicastEvent(new OrderEvent("O-SYNC"));
        } catch (IllegalStateException ex) {
            System.out.println("SYNC_CAUGHT=" + ex.getMessage());
        }
    }

    private static void asynchronousExample() throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "event-worker"));

        try {
            CountDownLatch allowFailure = new CountDownLatch(1);
            CountDownLatch errorSeen = new CountDownLatch(1);
            CountDownLatch otherListenerSeen = new CountDownLatch(1);
            AtomicReference<String> recordedFailure = new AtomicReference<>();

            var multicast = new SimpleApplicationEventMulticaster();
            multicast.setTaskExecutor(executor);

            multicast.setErrorHandler(error -> {
                recordedFailure.set(
                        error.getClass().getSimpleName() + ":"
                        + error.getMessage());
                errorSeen.countDown();
                // Return normally: suppress the exception at this boundary.
            });

            multicast.addApplicationListener(
                    new ApplicationListener<OrderEvent>() {
                        @Override
                        public void onApplicationEvent(OrderEvent event) {
                            try {
                                if (!allowFailure.await(5, TimeUnit.SECONDS)) {
                                    throw new IllegalStateException(
                                            "publisher did not release task");
                                }
                            } catch (InterruptedException interrupted) {
                                Thread.currentThread().interrupt();
                                throw new IllegalStateException(
                                        "listener interrupted", interrupted);
                            }
                            throw new IllegalStateException(
                                    "async failure " + event.orderId());
                        }
                    });

            multicast.addApplicationListener(
                    new ApplicationListener<OrderEvent>() {
                        @Override
                        public void onApplicationEvent(OrderEvent event) {
                            otherListenerSeen.countDown();
                        }
                    });

            multicast.multicastEvent(new OrderEvent("O-ASYNC"));
            System.out.println("ASYNC_PUBLISH_RETURNED");
            allowFailure.countDown();

            if (!errorSeen.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("ErrorHandler did not observe failure");
            }
            if (!otherListenerSeen.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Other listener did not run");
            }

            System.out.println("ERROR_HANDLER=" + recordedFailure.get());
            System.out.println("OTHER_LISTENER_RAN=true");
        } finally {
            executor.shutdownNow();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        synchronousExample();
        asynchronousExample();
    }
}
```

Run command from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

Lines **printed by the program itself**, excluding environment-dependent logs:

```text
SYNC_CAUGHT=sync failure
ASYNC_PUBLISH_RETURNED
ERROR_HANDLER=IllegalStateException:async failure O-ASYNC
OTHER_LISTENER_RAN=true
```

### 8.2. Why Is the Output Deterministic?

1. `synchronousExample()` uses a multicaster without an executor or `ErrorHandler`. The listener throws `IllegalStateException("sync failure")`; `multicastEvent(...)` runs on the same thread so the outer `catch` catches it.
2. `asynchronousExample()` uses an `ExecutorService` with a dedicated worker. The first listener task is blocked from throwing until `allowFailure` is released.
3. The publisher calls `multicastEvent(...)`, prints `ASYNC_PUBLISH_RETURNED`, **and only then** calls `allowFailure.countDown()`. Thus the listener error is guaranteed to occur **after** the publisher returns.
4. When the listener throws `IllegalStateException`, `SimpleApplicationEventMulticaster` invokes `ErrorHandler`; the handler records the type and message, counts down the latch, and returns without rethrowing.
5. The remaining listener runs via the task executor; two latches with timeouts confirm both the `ErrorHandler` and the second listener completed observation.
6. Only after both latches are satisfied does `main` print the last two lines. Hence the output does not depend on whether the scheduler runs the worker quickly or slowly.
7. The `finally` block shuts down the executor so no threads linger after the demo. `shutdownNow()` is solely demo-end cleanup; production applications need graceful shutdown per business requirements.

### 8.3. What the Demo Does Not Prove

- It does **not** run a real Spring `ApplicationContext`; the example uses `SimpleApplicationEventMulticaster` directly to isolate dispatch error behavior.
- It does **not** send messages to a broker or guarantee retries/durability.
- It does **not** simulate the `@Async` annotation or `FutureTask.submit()`, so it does not demonstrate handlers for those mechanisms via execution.
- It only proves a custom `ErrorHandler` **suppresses** errors. Replacing it with a rethrowing handler alters the worker exception path, even though the publisher has already returned.
- It uses no transactions or database; there is no rollback semantics.

To integrate into a Spring app, expose the executor/error handler on the bean named `applicationEventMulticaster` as in section 4 and write dedicated integration tests.

## 9. When the Executor Handles Exceptions Itself: execute vs. submit

This is a major source of confusion when inspecting `ThreadPoolTaskExecutor` or JDK `ExecutorService`.

### 9.1. execute(Runnable)

With `Executor.execute(Runnable)`, a task throwing an unchecked exception directly can escape the worker thread. Depending on the executor implementation, the exception may be recorded via logs, `afterExecute`, or `UncaughtExceptionHandler`; the worker thread may be replaced.

```java
executor.execute(() -> {
    throw new IllegalStateException("execute failed");
});
```

This is an illustrative snippet. Errors do not automatically travel back to the `execute(...)` call on the other thread once the task is accepted and runs asynchronously. However, if rejection occurs right at submission, `execute(...)` can still throw on the caller.

### 9.2. submit(Runnable/Callable)

With `ExecutorService.submit(...)`, errors thrown by the task are typically captured inside the returned `Future`:

```java
Future<?> future = executor.submit(() -> {
    throw new IllegalStateException("submit failed");
});

try {
    future.get();
} catch (ExecutionException ex) {
    Throwable original = ex.getCause();
    // original is the error thrown inside the Callable/Runnable.
}
```

This is a snippet requiring imports for `Future`, `ExecutionException`, and a defined `executor`; `future.get()` can throw `InterruptedException` so callers must handle or declare it. In the `submit failed` example, `future.get()` typically throws `ExecutionException` wrapping `IllegalStateException`.

**Do not treat `execute()` and `submit()` as equivalent in how errors surface.** If nobody keeps the `Future` or calls `get()`/a completion handler, an error stored inside the `Future` may never appear where you are watching.

### 9.3. CompletableFuture

With `CompletableFuture`:

```java
CompletableFuture<Void> task = CompletableFuture.runAsync(
        () -> sendEmail(),
        executor);

task.whenComplete((ignored, error) -> {
    if (error != null) {
        logger.error("Async email failed", error);
    }
});
```

This is an illustrative snippet requiring `CompletableFuture`, `executor`, `sendEmail()`, and `logger`. A failing task causes the future to complete exceptionally. `join()` typically throws `CompletionException`, whereas `get()` throws `ExecutionException`. Completion callbacks may run on the thread completing the task or another thread depending on the API; do not assume MDC/transactions exist without propagation.

**Important:** standard `SimpleApplicationEventMulticaster` submits listeners via `Executor.execute(...)`, yet a listener might **create a Future itself** internally. In that case the multicaster's `ErrorHandler` has no visibility into exceptions handled asynchronously inside that Future later.

## 10. UncaughtExceptionHandler, afterExecute, and TaskDecorator

### 10.1. Thread.UncaughtExceptionHandler Only Sees Unintercepted Errors

A thread factory can attach a handler:

```java
ThreadFactory factory = task -> {
    Thread thread = new Thread(task, "event-worker");
    thread.setUncaughtExceptionHandler((t, error) ->
            logger.error("Uncaught in " + t.getName(), error));
    return thread;
};
```

This is illustrative configuration; requires `ThreadFactory`, `logger`, and an executor creating threads from the factory. This handler **cannot** observe errors if:

- The multicaster's `ErrorHandler` already suppressed them.
- The `@Async void` interceptor handed the error to `AsyncUncaughtExceptionHandler` without rethrowing.
- `FutureTask` captured the error to report via `get()` later.
- The listener caught the error itself and recorded nothing.

Therefore, **configuring an `UncaughtExceptionHandler` does not mean catching every event failure**.

### 10.2. ThreadPoolExecutor.afterExecute

JDK `ThreadPoolExecutor.afterExecute(Runnable, Throwable)` provides a hook to inspect a task after execution. For tasks from `submit`, the `Throwable` parameter can be `null` even when the task failed, because `FutureTask` catches exceptions internally. Per the JDK pattern, check whether `Runnable` is a `Future<?>` and call `get()` once done.

```java
@Override
protected void afterExecute(Runnable runnable, Throwable failure) {
    super.afterExecute(runnable, failure);

    if (failure == null && runnable instanceof Future<?> future) {
        try {
            future.get();
        } catch (CancellationException ex) {
            failure = ex;
        } catch (ExecutionException ex) {
            failure = ex.getCause();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
    }

    if (failure != null) {
        reportTaskFailure(failure);
    }
}
```

This is an **illustrative override** inside a `ThreadPoolExecutor` subclass, requiring imports for `Future`, `CancellationException`, `ExecutionException`, and a `reportTaskFailure` method. It is not a standalone class or mandatory configuration. For cancellations, the alert severity policy may differ from execution failures. If the runnable had not finished at the hook, calling `get()` could block; in a standard executor's `afterExecute`, the task has just finished, yet interruption must still be handled.

Even with this hook, you **will not see listener errors already suppressed by the multicaster's `ErrorHandler`**, because by the time the task reaches the executor it no longer throws.

### 10.3. TaskDecorator

`ThreadPoolTaskExecutor.setTaskDecorator(...)` is commonly used to propagate MDC/tracing context or wrap a `Runnable`. It can record errors in a plain `execute` wrapper:

```java
executor.setTaskDecorator(task -> () -> {
    try {
        task.run();
    } catch (RuntimeException ex) {
        logger.error("Executor task failed", ex);
        throw ex;
    }
});
```

This is an illustrative configuration snippet; requires initialized `executor` and `logger`. It does not replace a listener `ErrorHandler`: wrapper ordering and catching mechanisms determine whether the decorator sees the exception.

Spring Javadoc notes that `TaskDecorator` observes exceptions differently between `execute` and `submit`: on the `submit` path, the decorator may receive a `FutureTask` that does not throw externally, so a `catch` in the wrapper **does not catch errors retained inside the Future**.

Do not pick a decorator solely intending to "catch every exception" while ignoring Future or `ErrorHandler` semantics.

## 11. @Async void and AsyncUncaughtExceptionHandler

When Spring `@Async` handles a `void`-returning method, the caller has no `Future` to inspect errors. Spring provides:

```java
public interface AsyncUncaughtExceptionHandler {
    void handleUncaughtException(
            Throwable ex, Method method, Object... params);
}
```

The snippet above describes the API contract; `AsyncUncaughtExceptionHandler` is in `org.springframework.aop.interceptor` and `Method` is in `java.lang.reflect`.

Sample configuration:

```java
@Configuration(proxyBeanMethods = false)
@EnableAsync
class AsyncEventConfig implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (error, method, params) -> {
            logger.error("Async listener failed: " + method.getName(), error);
        };
    }
}
```

This is an illustrative snippet requiring Spring imports and a logger. It does not create a fixed event executor; you can configure `getAsyncExecutor()` or a separate executor bean.

For `@Async` methods returning `Future` or `CompletableFuture`, the caller has a path to observe failures from the Future; errors may **not pass through `AsyncUncaughtExceptionHandler`** like `void` methods. Thus the choice of return type directly affects error testing and operations.

### Two Easily Confused Points

- `AsyncUncaughtExceptionHandler` is not `SimpleApplicationEventMulticaster.setErrorHandler`.
- With `@Async @EventListener void`, exceptions may be handled by the async interceptor **after the listener proxy call has already returned** to the multicaster. The multicaster's `ErrorHandler` cannot directly observe errors inside the downstream task if the async layer already handled them.

In event listener design, you rarely need an `@Async` listener returning a Future just for the publisher to wait on it: the event-publishing contract does not expose Futures that way. If business logic needs a synchronous result to decide next steps, an explicit service method or command/result API is usually more appropriate.

## 12. Why Do Errors Appear Only on the Worker Thread?

Suppose logs look like:

```text
http-nio-8080-exec-4 INFO  Order placed: O-100
domain-event-3       ERROR Event listener failed
java.lang.IllegalStateException: SMTP unavailable
```

Several plausible causes:

1. The publisher only submitted the event listener task without waiting for completion.
2. The listener threw an exception on the executor thread.
3. The multicaster's `ErrorHandler` logged and suppressed it, or executor/JVM logging recorded an uncaught failure.
4. The HTTP request already returned a success response before the error surfaced.
5. MDC and `traceId` contexts were not propagated, so worker logs lack the original request info.

**Do not conclude that the executor retried automatically or Spring rolled back automatically.** Normally, Spring Application Events are an in-process mechanism without a durable queue or automatic business-semantic retries.

### Do Not Look Only at HTTP Status

HTTP 200/201 may mean the **place order** step succeeded while the asynchronous **send email** step failed. This can be valid by design if email is a side effect that does not determine the primary transaction.

Conversely, if business success **must** depend on the email or an external call, returning 200 before that step finishes may violate the contract. Redesign synchronization/transactions/orchestration rather than merely adding logging to `ErrorHandler`.

### Do Not Look Only at the "Published" Log

`logger.info("Event published")` right after `publishEvent(...)` in async mode proves only that **the publish/submit call passed that line**, not that all listeners succeeded. Place corresponding logs inside listeners after completing side effects; if durability is needed, persist processing state durably.

## 13. Logging, Tracing, and Contextual Information

When a listener runs on another executor thread, ThreadLocals are typically **not transferred automatically**:

- Spring Security's `SecurityContextHolder` from the request thread.
- Custom `TenantContext`.
- MDC used for request ID / traceId / spanId.
- Thread-bound transaction context.
- Custom application ThreadLocals.

If a listener fails and logs lack trace IDs, errors can appear to "belong to no request". Spring Framework offers `ContextPropagatingTaskDecorator` alongside Micrometer Context Propagation to help carry configured contexts across executors.

Conceptual configuration example:

```java
executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
```

This is a snippet requiring Spring Framework 6.1+, compatible Micrometer Context Propagation, and a `ThreadPoolTaskExecutor` bean. It does not guarantee every security/tenant context transfers automatically: check registry/accessors, versions, policies, and trust boundaries.

**Important:** propagating context for logging does not make it safe to execute arbitrary operations under the old request's privileges. For async events running after user permissions may have changed, consumers must use verified identity/tenant metadata and dedicated policies rather than treating ThreadLocals as authorization.

### Minimal Useful Metadata for Errors

A domain event can carry:

```java
public record OrderPlaced(
        String eventId,
        String orderId,
        String tenantId,
        String correlationId) {
}
```

This is an illustrative record. `eventId` identifies the occurrence, `orderId` ties the fact to the aggregate, `tenantId` must be validated by the producer at the business source, and `correlationId` links the workflow. Never put JWTs/access tokens or full `Authentication` objects into events just to "keep context".

In `ErrorHandler`, if specific event IDs need to be logged, place observability logging close to the handler that knows the event or use a wrapper/adapter; `ErrorHandler` receives a `Throwable` and does not automatically carry event metadata. Protect PII and metric cardinality.

## 14. Transactions and Async Exceptions: Do Not Assume Rollback

Common scenario:

```java
@Transactional
public void placeOrder(PlaceOrderCommand command) {
    Order order = orderRepository.save(...);
    applicationEventPublisher.publishEvent(
            new OrderPlaced(order.getId()));
}
```

This is application pseudocode, not part of section 8's runnable project. If the publisher uses an async multicaster:

1. `placeOrder`'s transaction lives on the publisher thread.
2. The async listener may start before the transaction commits or after it commits, depending on scheduling.
3. Listener exceptions normally do not propagate back to the publisher to roll back the original transaction.
4. Async listeners do not automatically share the same transaction context; reading newly saved data may see uncommitted state or miss rows depending on isolation/database.
5. Once the original transaction commits, a failing callback cannot "undo" the commit simply by throwing on a worker.

With `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`, Spring synchronizes the callback with the transaction phase; however, this callback has its own semantics and does not automatically become asynchronous merely because a multicaster executor is configured.

Use after-commit for side effects valid only after commit, yet **do not treat after-commit callbacks as durable queues**. A process crash can still lose work when relying solely on in-memory events. For critical business flows, consider a transactional outbox, a broker with ack/retry/dead-letter support, and idempotent consumers.

### When Must Errors Be Returned to the Publisher?

If listener processing is a mandatory condition for considering the command successful, establish an explicit contract:

- Call the synchronous service directly and receive its result/exception.
- Use a stateful workflow tracking processing outcomes (pending/succeeded/failed).
- Use orchestration/saga when steps are distributed with no shared transaction.

You cannot pull an exception from an async task back into the "past" of an HTTP request merely by wrapping `publishEvent(...)` in a `catch`.

## 15. Error Policy: Suppressing Does Not Mean Solved

An `ErrorHandler` decision should reflect event criticality:

| Work type | Example | Recommended policy |
| --- | --- | --- |
| Best-effort telemetry | Secondary metrics, non-critical analytics | May log + count + suppress per SLO; still track failures |
| Retryable notifications | Emails, webhooks | Persist state, bounded retries, idempotency, alerts |
| Critical projection updates | Read models, materialized views | Durable queue/outbox, retry/dead-letter, offset/progress |
| Mandatory transactional step | Inventory check before confirming order | Do not hide in best-effort async events; use sync/tx contract |
| Compliance audit | Mandatory history logging | Choose durable, provable storage rather than logs alone |
| Data-error tasks | Invalid event payload | Log structured failure, quarantine poison event, avoid infinite retries |

**Suppress** means "do not let the exception continue escaping from the listener", not "success". You must have metrics and a policy deciding whether the event gets retried or requires manual intervention.

An error can lead to at least three states:

```text
EVENT_ACCEPTED
      |
      +--> HANDLED_SUCCESS
      |
      +--> HANDLED_FAILED_RETRYABLE
      |
      +--> HANDLED_FAILED_TERMINAL
```

This is purely an application state model, not a built-in Spring state machine. To know long-term outcomes, store them durably rather than inferring from the publisher not throwing.

## 16. Testing ErrorHandler and Executors Properly

### 16.1. Use Latches to Avoid Flaky Tests

Synchronous test:

```java
assertThrows(IllegalStateException.class,
        () -> multicast.multicastEvent(new OrderEvent("O-1")));
```

This is a JUnit snippet assuming `multicast` has no async executor/suppressing `ErrorHandler` and the listener throws `IllegalStateException`.

Async test:

```java
CountDownLatch errorObserved = new CountDownLatch(1);
AtomicReference<Throwable> failure = new AtomicReference<>();

multicast.setErrorHandler(error -> {
    failure.set(error);
    errorObserved.countDown();
});

multicast.multicastEvent(new OrderEvent("O-2"));

assertTrue(errorObserved.await(5, TimeUnit.SECONDS));
assertInstanceOf(IllegalStateException.class, failure.get());
```

This is a **test snippet** requiring JUnit, `java.util.concurrent` imports, an executor-backed multicaster, and a failing listener—not a standalone runnable example. The latch uses a timeout so tests fail clearly if the handler does not run; `AtomicReference` captures the exact exception instead of relying on logs.

### 16.2. Verify Both Errors and Side Effects

Do not only assert the handler was called. A practical test should verify:

- Was the right listener or worker invoked?
- Do exception type/message/cause match the expected source?
- Were **partial** side effects accidentally executed before the exception occurred?
- Was the error logged/metered/recorded?
- Are retries enabled or not, and what are backoff/deduplication policies?
- Do other listeners still execute as designed or get blocked?
- Do remaining tasks need cancellation or shutdown?
- Does the publisher receive or not receive the exception per sync/async contract?
- Is there ThreadLocal/tracing context leakage into subsequent tasks?

If a listener sent an email and then threw before recording state, a retry could send **two emails**. A technically sound `ErrorHandler` still does not replace business operation idempotency.

### 16.3. Test Rejection and CallerRuns Separately

To test queue saturation, configure a very small executor, hold the worker with a `CountDownLatch`, fill the queue to capacity, and submit one more task. Tests must use timeouts and cleanup to avoid hanging CI.

Then measure:

- `AbortPolicy`: does rejection happen, and how does the multicaster handle it in your version?
- `CallerRunsPolicy`: does the listener run on the publisher thread and affect latency?
- `DiscardPolicy`: are tasks dropped without error reporting?
- Pool shutdown: does the executor/multicaster fall back, throw, or drop tasks?

Do not build tests around `Thread.sleep(50)`. Use latches, counters, thread identities, and explicitly declared executor policies.

### 16.4. Testing submit/Future

For tasks submitted returning a Future, verify:

```java
Future<?> future = executor.submit(
        () -> { throw new IllegalStateException("boom"); });

ExecutionException ex = assertThrows(
        ExecutionException.class,
        future::get);

assertInstanceOf(IllegalStateException.class, ex.getCause());
```

This is a JUnit snippet requiring `ExecutorService`, `Future`, `ExecutionException`, and assertions. Do not assume `Thread.UncaughtExceptionHandler` is invoked for errors already captured inside `FutureTask`.

## 17. Quick Debugging When "Errors Disappear"

A diagnostic workflow you can apply directly on a Spring project:

**Step 1 — Identify the publisher and event type.** Locate `publishEvent(...)`; record whether it runs in a request, scheduler, or transaction phase.

**Step 2 — Find the actual multicaster.** Is there an `applicationEventMulticaster` bean? Are `SimpleApplicationEventMulticaster.setTaskExecutor(...)` and `setErrorHandler(...)` configured?

**Step 3 — Inspect the listener.** Is it `@EventListener`, `@Async`, `@TransactionalEventListener`, or a handler launching its own `CompletableFuture`? These follow different exception paths.

**Step 4 — Identify where tasks are sent.** One executor or many? What are thread names, pool state, queue size, rejection policy, active threads, and pending tasks?

**Step 5 — Find the error interception point.** Caught inside listener? Multicaster `ErrorHandler` logging/suppressing? `AsyncUncaughtExceptionHandler`? Future completion? `TaskDecorator`? `UncaughtExceptionHandler`? Executor `afterExecute`?

**Step 6 — Inspect root error info.** Use exception types, stack traces, and causal chains. If logs only print `error.getMessage()`, you may lose the cause and call path needed for debugging.

**Step 7 — Check transactions.** Has the publisher committed or is it still in a transaction? Did the listener run before commit? Does the listener error belong to the business transaction or only a side effect?

**Step 8 — Verify outcomes.** Were side effects partially completed? Is there a durable `FAILED`/`PENDING` record or only a log line?

**Step 9 — Check duplicates/retries.** Might the publisher have retried, the executor fallen back to caller-runs, or the consumer redelivered? Is listener idempotency ensured?

**Step 10 — Build a reproducible test.** Test sync and async separately with latches, asserting handler invocation/non-invocation, plus rejection and shutdown if relevant.

### Symptom Table

| Symptom | Likely cause | What to check |
| --- | --- | --- |
| Publisher succeeds, listener logs error on worker | Async task accepted then threw | Executor + `ErrorHandler` |
| Publisher catches nothing yet handler increments counter | Handler suppressed error | Handler policy and business outcome |
| No errors in logs, side effect missing | `FutureTask` holds error, `DiscardPolicy` drops task, listener catches/suppresses | Future, rejection, logging |
| Error surfaces on caller despite configured executor | Sync-only listener, `CallerRunsPolicy`, or rejection fallback | Thread identity, version, policy |
| Error appears in `AsyncUncaughtExceptionHandler` | `@Async void` method failed | `AsyncConfigurer`/annotation proxy |
| Future completes exceptionally, no uncaught log | Exception stored in Future | `get()`, completion callbacks |
| Second listener still runs when first fails | Async per-listener tasks or suppressing handler | Do not infer all tasks succeeded |
| Missing transaction context on worker | Thread-local tx does not auto-propagate | Transaction boundary, event phase |
| Error log missing `traceId` | MDC/tracing context not propagated | `TaskDecorator`, Context Propagation |
| Duplicate side effects after retry | Handler lacks idempotency/outcome tracking | Dedupe key, retry strategy |
| Shutdown occasionally runs events on caller | Executor rejected and multicaster fell back | Source/version, shutdown plan |

## 18. Anti-Patterns to Avoid

1. **Wrapping only `publishEvent(...)` in `try/catch` and believing all listeners are safe.** Works for some sync/submit errors, not already-accepted async tasks.
2. **Configuring an `ErrorHandler` that simply returns with no logs/metrics.** Turns failures into complete silence.
3. **Assuming the multicaster's `ErrorHandler` catches exceptions inside listener-created `CompletableFuture`s.** Those errors live in a separate Future layer.
4. **Assuming `@Async void` always throws back to the publisher.** Must check `AsyncUncaughtExceptionHandler`.
5. **Relying on `Thread.UncaughtExceptionHandler` to catch every task error.** `FutureTask` and suppressing handlers keep exceptions from escaping `Runnable`.
6. **Assuming a full executor queue always throws.** Rejection handlers may run on caller or silently discard.
7. **Assuming executor rejections always propagate out of the multicaster.** Some implementations/versions fall back to running listeners on the caller.
8. **Failing to distinguish submission errors from execution errors.** Leads investigation down the wrong path.
9. **Using `DiscardPolicy` for important business events.** Work is lost while the caller still sees success.
10. **Using an unbounded queue to "avoid rejections".** Accumulates backlogs, causing memory pressure and slow shutdowns.
11. **Logging raw events containing secrets/PII.** Fixes operations at the cost of a security breach.
12. **Failing to clear MDC/tenant ThreadLocals on workers.** Subsequent tasks may inherit the wrong context.
13. **Ignoring transaction boundaries.** Async failures do not mean the DB rolled back.
14. **Retrying without idempotency.** Side effects may have partially executed before the failure.
15. **Omitting timeouts in async tests.** CI can hang indefinitely when tasks never run.
16. **Using `Thread.sleep(...)` instead of completion conditions.** Tests flake on slow machines.
17. **Treating Spring Application Events as a broker with durable retries.** By default it is in-process/context dispatch only.
18. **Configuring both a multicaster executor and `@Async` without knowing which handler sees exceptions.** Creates multiple hard-to-diagnose interception layers.
19. **Hiding the original exception via `throw new RuntimeException("error")` without cause.** Destroys stack traces and hinders root-cause analysis.
20. **Confusing "listener received event" with "listener side effect succeeded".** Measure real outcomes.

## 19. Operations Checklist

Before concluding "the exception was handled by the executor", answer:

- [ ] Is the multicaster synchronous or configured with `setTaskExecutor(...)`?
- [ ] Does the listener use `@Async` or create a `Future` internally?
- [ ] Did the error happen at `execute/submit` or after the worker started?
- [ ] Does the multicaster's `ErrorHandler` log, suppress, or rethrow?
- [ ] Is `AsyncUncaughtExceptionHandler` configured for `@Async void`?
- [ ] Is `Future.get()/join()/whenComplete()` used to observe task failures?
- [ ] Do `TaskDecorator` and `Thread.UncaughtExceptionHandler` even see this error path?
- [ ] Does the pool have a bounded queue, explicit rejection policy, and clear shutdown behavior?
- [ ] Which listeners do not support async execution?
- [ ] Are errors logged with stack traces and safe event correlation?
- [ ] Are there separate metrics for accepted/failed/rejected/retried/succeeded?
- [ ] Can events be lost on process crash? Is an outbox/broker needed?
- [ ] Are consumers idempotent if retried?
- [ ] Are transaction semantics preserved as required?
- [ ] Do tests have latches/timeouts and verify exceptions at the exact boundary?

**Summary:** Exceptions in Spring event listeners can pass through multiple layers. For executor-executed listeners, errors occurring after task acceptance **do not automatically return to the thread calling `publishEvent()`**. `SimpleApplicationEventMulticaster.ErrorHandler` governs listener error handling at dispatch; `@Async void` uses `AsyncUncaughtExceptionHandler`; `submit`/`Future` tasks hold errors until results are retrieved. Submission/rejection errors take a separate path, occasionally triggering caller-runs/fallback. Systems must record **outcomes, stack traces, and context**, and design proper retries/idempotency rather than treating a normal publisher return as proof that every listener succeeded.

## References

- [Spring Framework 6.2 — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.2 — ApplicationListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationListener.html)
- [Spring Framework — Observability and Application Events](https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html)
- [JDK 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [JDK 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)