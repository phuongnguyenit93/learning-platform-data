# TaskDecorator Wraps Tasks to Set Up and Clean Up Context

## 1. Why Can Asynchronous Tasks Lose Context?

In Spring Framework, calls via `@Async` or `ThreadPoolTaskExecutor` typically execute work on a **worker thread different from the caller thread**. This gives rise to a subtle bug: the caller has a request ID in `ThreadLocal` or MDC for logging, yet inside the async task the value is `null`; conversely, a reused worker retains the context **of the previous request**, causing mixed-up logs, traces, or even cross-task data leaks.

`ThreadLocal` binds data **to each thread**, not to a logical request, a `Runnable`, or a `Future`. A thread pool reuses workers across many tasks. Therefore, what the caller sets on its own thread **does not automatically appear** on the worker, and what the worker stored previously does not automatically vanish when a task finishes.

`TaskDecorator` in Spring is an extension point for **wrapping a task in another `Runnable`**. A decorator is commonly used to:

1. **Capture an appropriate context snapshot** on the calling thread at the moment the executor receives the work.
2. **Install the snapshot on the worker** right before delegating to `Runnable.run()`.
3. **Run the original task**.
4. **Restore the worker's prior context, or clear it completely if none existed initially**, in `finally`, even if the work fails.

This is a **capture → set → run → restore/clear** pattern, crucial when workers are reused. This lesson explains that mechanism, `ThreadPoolTaskExecutor` integration, a runnable Java 17+ demo, MDC usage, security/transaction boundaries, and testing against context leaks.

## 2. What Is TaskDecorator, and Where Does It Sit in the Task Path?

Spring declares the functional interface:

```java
@FunctionalInterface
public interface TaskDecorator {
    Runnable decorate(Runnable runnable);
}
```

This is the **concise, core signature** of `org.springframework.core.task.TaskDecorator`. `decorate` receives the callback about to be executed by the executor and **returns a new `Runnable`**, responsible for eventually invoking `runnable.run()`. The key part is not transforming input data, but creating an **execution scope** around execution.

Typical flow:

```text
Caller thread                                   Pool worker thread
-------------                                   ------------------
MDC / ThreadLocal has requestId=REQ-7
          |
          v
executor.submit(task)
          |
          v
TaskDecorator.decorate(callback)
          |
          +-- capture requestId="REQ-7"
          |
          +-- return wrapped Runnable ---------+
                                               |
                                        worker picks up callback
                                               |
                                        save previous context
                                               |
                                        set requestId="REQ-7"
                                               |
                                        callback.run()
                                               |
                                           finally
                                               |
                                        restore / remove
                                               |
                                        worker returns to pool
```

**Critical timing:** context capture must happen **at submission on the caller thread**; do not wait until `run()` on the worker to read from `ThreadLocal`, because the worker has its own thread-local storage. The job of the returned `Runnable` is to install the captured snapshot onto the worker.

This does not mean every `TaskExecutor` implementation guarantees switching to another thread. `TaskDecorator` only wraps the executed callback; which thread actually runs depends on the executor. Context handoff benefits are clearest in `ThreadPoolTaskExecutor`, where workers are separate from the caller.

## 3. Three Entities to Distinguish: Caller Context, Captured Snapshot, and Worker Context

To avoid overwriting or leaving data behind, keep these separate:

| Entity | Where Does It Live? | When Read/Written | Responsibility |
| --- | --- | --- | --- |
| **Caller context** | `ThreadLocal` or MDC on the calling thread | Exists before task submission | Provides the values to propagate |
| **Captured snapshot** | Variable closed over by the decorator `Runnable` | Captured when `decorate` is called | Holds an immutable/independent value for that specific task |
| **Worker previous context** | `ThreadLocal` or MDC already present on the worker | Read right before running the task | Must be restored in `finally`, even if the task errors |
| **Worker current context** | Context installed for the current task | During `runnable.run()` | Used for logging/tracing/logic as required |
| **Cleanup state** | Worker after the task | After `finally` runs | Leaves no context behind from the current task |

For example, before running task A, the worker has no request ID. When A runs, the decorator sets `A`. When A finishes, it must **remove** it so A does not remain on the worker for B to misread. If the worker already had another valid context (for instance, from an outer wrapper), the decorator must **restore the old value**, not wipe it blindly. This is why a `previous` variable is needed rather than unconditionally calling `ThreadLocal.remove()`.

A proper snapshot is usually a **value**, not a reference to a mutable request object. If you capture a `Map` that the caller can mutate after submitting, tasks no longer have a reliable snapshot; copy the needed data or use a dedicated snapshot API.

## 4. Standard TaskDecorator Pattern: Capture on Submit, Restore in finally

Implementation idea with `ThreadLocal<String>`:

```java
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

TaskDecorator decorator = runnable -> {
    String captured = REQUEST_ID.get(); // Read on caller thread.
    return () -> {
        String previous = REQUEST_ID.get(); // Read on worker thread.
        try {
            if (captured == null) {
                REQUEST_ID.remove();
            } else {
                REQUEST_ID.set(captured);
            }
            runnable.run();
        } finally {
            if (previous == null) {
                REQUEST_ID.remove();
            } else {
                REQUEST_ID.set(previous);
            }
        }
    };
};
```

This is an **illustrative Java snippet**, placed inside a class importing `org.springframework.core.task.TaskDecorator` and declaring `REQUEST_ID`. It expresses the complete policy for a simple context key:

- `captured` is read **before the Runnable is handed off to the worker**.
- `previous` is read on the **worker** to protect an existing scope.
- If the caller has no ID, the ID must be removed on the worker for the duration of the task to avoid misreading a previous request.
- `runnable.run()` may succeed or throw an exception. `finally` runs in both cases when control leaves `try`.
- After the task, the worker returns to its prior context; if initially empty, it returns to empty.

**Do not use the pattern below:**

```java
// WRONG: sets context but forgets cleanup/restore.
return () -> {
    REQUEST_ID.set(captured);
    runnable.run();
};
```

This is a **counter-example snippet**; the worker thread may retain `captured` after finishing. If `captured == null`, calling `set(null)` also does not mean the same as remove: `ThreadLocal.remove()` explicitly deletes the entry from ThreadLocalMap, avoiding holding unnecessary references on long-lived workers.

## 5. Runnable Spring Framework 6.2.9 + Java 17+ Example

The following example uses `ThreadPoolTaskExecutor.setTaskDecorator` directly with a single reused worker. It demonstrates three scenarios:

1. Context `req-169` from the caller is captured and present when the first task runs.
2. The second task throws `IllegalStateException`; the error is received via `Future.get()`.
3. After clearing the caller context, a subsequent task does not see the old context. The decorator also verifies that the worker context is already empty **before installing the new context**.

Maven structure:

```text
task-decorator-demo/
├── pom.xml
└── src/main/java/demo/TaskDecoratorDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>task-decorator-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/TaskDecoratorDemo.java`:

```java
package demo;

import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.core.task.TaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class TaskDecoratorDemo {

    private static final ThreadLocal<String> TRACE = new ThreadLocal<>();
    private static final AtomicBoolean WORKER_CLEAN = new AtomicBoolean(false);

    private static TaskDecorator capturedTraceDecorator() {
        return task -> {
            String submittedTrace = TRACE.get(); // Thread submitting the task.

            return () -> { // Worker thread runs this block.
                String previous = TRACE.get();

                // Prove the worker does not carry context from a previous task.
                if (submittedTrace == null) {
                    WORKER_CLEAN.set(previous == null);
                }

                try {
                    if (submittedTrace == null) {
                        TRACE.remove();
                    } else {
                        TRACE.set(submittedTrace);
                    }

                    task.run();
                } finally {
                    if (previous == null) {
                        TRACE.remove();
                    } else {
                        TRACE.set(previous);
                    }
                }
            };
        };
    }

    public static void main(String[] args) throws Exception {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        pool.setQueueCapacity(4);
        pool.setThreadNamePrefix("worker-");
        pool.setTaskDecorator(capturedTraceDecorator());
        pool.initialize();

        try {
            TRACE.set("req-169");
            Future<String> first = pool.submit(() -> {
                return TRACE.get();
            });
            System.out.println("first = " + first.get());

            TRACE.set("req-fail");
            Future<?> failed = pool.submit(() -> {
                throw new IllegalStateException("boom");
            });
            try {
                failed.get();
            } catch (ExecutionException ex) {
                System.out.println("failure = "
                        + ex.getCause().getClass().getSimpleName());
            }

            TRACE.remove();
            Future<String> second = pool.submit(() -> {
                return String.valueOf(TRACE.get());
            });
            System.out.println("second = " + second.get());
            System.out.println("worker clean = " + WORKER_CLEAN.get());
            System.out.println("caller clean = " + (TRACE.get() == null));
        } finally {
            TRACE.remove();
            pool.shutdown();
        }
    }
}
```

Run in the project directory with Maven and JDK 17 or newer:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.TaskDecoratorDemo
```

Program stdout:

```text
first = req-169
failure = IllegalStateException
second = null
worker clean = true
caller clean = true
```

**Explanation of results:**

- The caller sets `TRACE=req-169` and submits. `TaskDecorator.decorate` captures this string when the calling thread hands off the job. `first.get()` waits for the worker to finish and prints `req-169`.
- The caller switches to `req-fail`. The second task is still captured/installed independently; it throws an exception. `Future.get()` throws `ExecutionException`; `getCause()` reveals the root `IllegalStateException`.
- After the failing task, the decorator's `finally` still restores the worker context prior to the task. The caller removes `TRACE` and submits the third task.
- Because the pool has only one worker and each step calls `get()` before submitting the next, the third task runs on the worker that processed the previous two tasks. `WORKER_CLEAN` checks `previous == null` right **before** the decorator clears/sets context for the third task. `true` is proof that cleanup worked on the reused worker in this example.
- The third task sees `TRACE.get() == null`; the caller also has no ID left. No old request data remains on the worker.

The example uses Spring Framework 6.2.9 to illustrate the stable API at that version. An equivalent class was executed against Spring 6.2.9 libraries on JShell, producing the exact five lines above; this verifies the main execution path, while the Maven configuration is presented as a reproducible project.

`TaskDecorator` is a **runtime callback**, not a business annotation. In a console program manually constructing an executor, you must call `initialize()` before use and `shutdown()` when done. For an executor declared as a Spring bean, the container manages its lifecycle; do not call `shutdown` per request.

## 6. Configuring TaskDecorator as a Spring Bean for @Async

In a Spring-managed application, set the decorator on the `ThreadPoolTaskExecutor` bean so every task **submitted through that specific executor** receives the wrapper. Configuration example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncContextConfig {

    @Bean("contextPool")
    public ThreadPoolTaskExecutor contextPool() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("context-");
        executor.setTaskDecorator(requestIdDecorator());
        return executor;
    }

    private TaskDecorator requestIdDecorator() {
        return task -> {
            String captured = RequestIdContext.get();
            return () -> {
                String previous = RequestIdContext.get();
                try {
                    RequestIdContext.setOrClear(captured);
                    task.run();
                } finally {
                    RequestIdContext.setOrClear(previous);
                }
            };
        };
    }
}
```

This is a **Spring configuration snippet requiring an application-defined `RequestIdContext` utility class**; `setOrClear(null)` must call `ThreadLocal.remove()`, not just `set(null)`. The numbers 4/8/100 are examples, not default production recommendations. When the bean is managed by Spring, the container initializes and shuts down the executor according to the context lifecycle.

A service using that executor:

```java
@Service
public class AuditService {

    @Async("contextPool")
    public CompletableFuture<String> writeAudit() {
        String requestId = RequestIdContext.get();
        // Run business logic and log using the requestId set on the worker.
        return CompletableFuture.completedFuture(requestId);
    }
}
```

This is also a **Spring integration snippet**, requiring `@Service`, `@Async`, and `CompletableFuture` imports. `@EnableAsync` must be enabled in the right application context, the caller must invoke the bean via its Spring proxy (not `new` or `this.writeAudit()` inside the same target), and `@Async("contextPool")` must select the bean that holds the decorator. If `@Async` picks another executor, the decorator attached to `contextPool` will **not automatically follow** that task.

In typical proxy mode, the interceptor dispatches the callback to the executor when receiving the call; the decorator captures context from the submitting thread. An async call traversing multiple executor layers may undergo **multiple context captures** at the respective boundaries; you must understand where new tasks originate and where the worker already carries context.

## 7. MDC Logging: Copying the Map and Cleaning the Right Scope

An application using SLF4J MDC often sets `traceId` or `requestId` on the caller thread:

```java
MDC.put("requestId", requestId);
```

`MDC` is typically backed by thread-bound context (depending on binding/implementation). With thread pools, do not assume the caller's MDC map follows onto the worker. Illustrative decorator pattern:

```java
TaskDecorator mdcDecorator = task -> {
    Map<String, String> captured = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            if (captured == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(captured);
            }
            task.run();
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    };
};
```

This is an **integration snippet**, requiring an SLF4J binding that supports MDC, imports `org.slf4j.MDC`, `java.util.Map`, `TaskDecorator`; it is not a standalone JDK program. `getCopyOfContextMap` returns a copy of the current map (or null), which is preferable to holding a shared mutable reference. `MDC.setContextMap` replaces the map on the executing thread, so restoring the old map in `finally` is mandatory.

Using `MDC.clear()` when there is no map both protects other requests and avoids leaving a thread-local map on the worker. Do not merely call `MDC.remove("requestId")` if the decorator replaced **the entire map**; it could drop or leave wrong other context keys. When an application has multiple context-wrapping layers, capture/restore ordering must be consistent.

**Do not copy arbitrary sensitive information into MDC.** Include only required safe IDs and logging attributes, never passwords, tokens, private information, or request bodies; MDC may be logged or shipped to external observability systems.

## 8. ContextPropagatingTaskDecorator: Built-In Option Since Spring 6.1

Spring Framework 6.1+ provides `org.springframework.core.task.support.ContextPropagatingTaskDecorator`, supporting propagation of certain execution contexts via the **Micrometer Context Propagation** ecosystem, especially useful for logging and observation/tracing contexts.

Configuration example when the required libraries and context accessors are present:

```java
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;

// Inside ThreadPoolTaskExecutor configuration:
executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
```

This is an **integration snippet**, not a standalone runnable Java file. When using it, verify a compatible Spring version, the Micrometer context-propagation dependency, and **registered ThreadLocalAccessor/context accessors**. This decorator cannot automatically know about every arbitrary `ThreadLocal` an application creates: without a matching accessor, that value may not be captured/restored.

The snapshot/scope mechanism avoids writing custom wrappers for common integrations, but it does not automatically carry or clone an open JDBC transaction. Javadoc also warns about overhead: for hundreds of thousands of tiny tasks, context capture/restore cost can be noticeable; measure before applying broadly.

If multiple decorators must be used together, Spring provides `CompositeTaskDecorator` in supported versions. Even when composing wrappers, understand execution and restore ordering; avoid mixing manual decorators and automatic propagation for the same context without defining who owns the scope.

## 9. Do Not Use InheritableThreadLocal as a Replacement for Per-Task Propagation

`InheritableThreadLocal` can transfer a value from parent thread to child thread **when the child thread is created**, yet a thread pool worker may exist long before a new request is handled. Consequently:

- A worker created during request A may inherit a value from A.
- That worker then serves requests B, C, and D without being recreated.
- `InheritableThreadLocal` **does not automatically update snapshots on each submission** and can cause wrong/lingering context.

Do not use thread inheritance to solve context propagation in reusable pools. Per-task capture and post-task restoration are far more appropriate. Some executors that spawn a new thread per task may exhibit different inheritance behavior, but that does not turn inheritance into a clear or safe mechanism across all executors.

## 10. Which Contexts Can Be Propagated, and Which Must Not Be Arbitrarily Copied?

| Context | Handling Approach | Why |
| --- | --- | --- |
| Correlation ID, request ID | Capture an immutable string, restore after execution | Well-suited for logging/tracing, minimal state |
| MDC Map | Copy snapshot and restore old Map | Workers are reused; avoid leftover keys |
| Tracing/observation context | Use Micrometer Context Propagation/compatible instrumentation | Requires accurate scope and lifecycle |
| Spring SecurityContext | Use Spring Security–supported SecurityContext propagation, verify principal/authorities and clean up | Naive copying of mutable context can be wrong or leak privileges |
| JDBC/JPA Transaction | **Do not** copy `TransactionSynchronizationManager`, `Connection`, or `EntityManager` to another thread | Imperative transactions and persistence contexts are typically tied to non-thread-safe threads/resources |
| Servlet request/response | Do not carry raw `HttpServletRequest`/`Response` to a worker after request scope ends | Container manages lifecycle; objects may become invalid |
| Locale/timezone | If needed, pass safe values and restore by scope | Do not assume caller locale appears on the worker |
| Reactor Context | Use Reactor-compatible context propagation integration | Reactor uses a context model different from `ThreadLocal` |
| Secret credentials/tokens | Minimize; use dedicated APIs/contexts when needed | Risk of sensitive data lingering on workers/logs |

**Do not use `TaskDecorator` to "transfer a transaction" by copying Spring's internal thread-locals.** Spring imperative transactions typically use `TransactionSynchronizationManager` to bind resources to a thread; moving a `Connection`/`EntityManager` to another worker violates lifecycle and concurrency safety. If a worker needs database work, open a transaction **on the worker** through an appropriate transactional service/proxy.

For example, an async service can call another bean annotated with `@Transactional` to establish a new transaction on the worker, then return an independent DTO. Context propagated by a decorator can carry correlation IDs for logging, while the **transaction boundary remains a separate responsibility**.

## 11. Error Handling: Decorator Does Not Replace Future.get()

A subtlety in Spring Javadoc: `TaskDecorator.decorate` may be applied to an **internal execution callback**, not necessarily the exact `Runnable`/`Callable` passed by the user. Especially with `submit(...)`, the callback is often a `FutureTask` or similar wrapper.

With `FutureTask`, the callable's exception is **recorded into the Future**, not always thrown directly out of `Runnable.run()`. Hence:

```java
return () -> {
    try {
        task.run();
    } catch (RuntimeException ex) {
        // May NOT catch business errors if task is a FutureTask.
        logFailure(ex);
        throw ex;
    } finally {
        restoreContext();
    }
};
```

This is a **counter-example snippet about assuming catch sees every error**, requiring application-defined `logFailure` and `restoreContext`. The `finally` block remains the right place for context cleanup, but `catch` around `run()` **is not a reliable monitoring mechanism for all errors in tasks submitted via `submit`**.

Read errors via `Future.get()` (catching `ExecutionException` and inspecting `getCause()`), or use `CompletableFuture.handle/whenComplete/exceptionally`, `AsyncUncaughtExceptionHandler` for `@Async void` methods, or API-appropriate observation points. The full Spring example in section 5 proves `failed.get()` observes `IllegalStateException`.

Distinguish clearly:

- **Submission/rejection errors:** the executor may throw `TaskRejectedException` immediately on the submit/caller side.
- **Execution errors:** the task was accepted and then threw an exception; `submit` usually surfaces this via the Future.
- **Context cleanup errors:** `finally` could throw its own exception; design `restore` reliably so it does not accidentally mask the business root cause.

A decorator should stay simple, perform no blocking I/O, never swallow delegate exceptions, and never rely on guessing Future state.

## 12. Cancellation, Timeouts, and Queuing Can Keep Context Alive Longer Than Expected

A context snapshot is captured at submission, yet the task may wait a long time before running. That leads to several consequences:

1. **The snapshot is the value at submission time**, not the latest state on the caller when the task actually starts.
2. A task waiting in a queue for a long time holds its snapshot, including object references if captured improperly. Avoid holding servlet requests, sessions, or large objects.
3. If a task is rejected on submission, the wrapper may have been created while `run()` is never called; handle rejection on the caller. Installing context **on the worker** does not occur if no worker executes.
4. If a Future is cancelled **before running**, a worker may execute a cancelled Future callback without running business logic, or the implementation may drop it from the queue; do not assume worker cleanup runs in every state. Avoid storing closeable resources in snapshots in the first place.
5. `get(timeout)` only limits how long the caller waits; it does not stop the worker or guarantee cleanup has run. `cancel(true)` does not forcibly halt all I/O; `finally` runs only when execution actually leaves the scope.
6. If a task spawns **a child task** on another executor, the first pool's decorator does not automatically attach to the second pool. To carry context across multiple boundaries, propagation must exist at each defined boundary.

Do not make the decorator depend on the request body/HTTP session after the request has finished. If only IDs/logging are needed, capture `String` values. For business data, create independent DTOs/value objects with clear lifecycles and bounds.

## 13. Testing Against Context Leaks on a Reused Pool

A test running **only a single task** and confirming it sees the request ID is insufficient. Because the worker has not been reused, you have not proven cleanup.

A meaningful test should:

1. Create a fixed pool with **one worker**, ensuring tasks run sequentially on the same thread.
2. Caller sets `requestId=A`, submits task A, waits for the result, and verifies the worker saw A.
3. Caller sets `requestId=B`, submits failing task B, verifies the exception reaches the caller and `finally` still ran.
4. Caller clears `requestId`, submits task C; the decorator checks the **existing context before set/clear** on the worker. It must be null if prior tasks cleaned up properly.
5. Inside task C, verify no request ID is present, and after C the worker remains clean. When testing nested scopes as well, verify **restoring previous** rather than always clearing.
6. Also test queue-full/rejection branches, caller interruption, timeout/cancellation, and long-running tasks.
7. Run concurrent tests with multiple requests carrying different IDs; verify no task misreads another task's ID and no memory/resource retention builds up over time.

The `TaskDecoratorDemo` example in section 5 performs steps 1–4 using `AtomicBoolean WORKER_CLEAN`. Do not check only task C's output, because a decorator that **starts with `remove()`** can mask the fact that task A left context behind. You must inspect `previous` right before setting the new context to genuinely detect leaks.

### Checking Logs and Traces

When working with MDC/observability, record correlation IDs on both caller and worker. Use safe IDs containing no sensitive information. Follow a single request across logs while ensuring no old request ID appears in new request logs. For trace context, verify parent–child span relationships with proper instrumentation; merely copying a `traceId` string into MDC does not create a valid span on its own.

## 14. Performance and Scope of Applicability

A decorator runs on the task submission path and its wrapper runs each time a task executes, so there is overhead:

- Snapshotting an MDC map may require copying key-value entries on every submission.
- Restoring context costs ThreadLocal operations and can retain references if implemented poorly.
- Multi-layered wrappers and unnecessary context capture add cost when tasks are ultra-short.
- Context propagation does not make a blocking API nonblocking, does not raise CPU or database limits, and does not make mutable data thread-safe.

Propagate only the **context genuinely needed** for logging, tracing, or business boundaries. If tasks merely compute a tiny operation without needing a request ID, a decorator may be unnecessary. If tasks perform long I/O and keeping correlation IDs helps debugging, decorator overhead is usually reasonable—though still worth measuring.

When using `@Async`, confirm which executor is actually selected; `setTaskDecorator` on bean A does not affect tasks running on bean B or `CompletableFuture.supplyAsync`'s common pool without an explicit executor.

## 15. Common Real-World Mistakes

1. **Capturing context at `run()` time on the worker.** By then the caller's `ThreadLocal` does not exist on the worker; capture at submission.
2. **Missing `finally`.** If a task throws an exception, context may be left on the worker serving the next request.
3. **Always calling `remove()` without restoring previous.** This can break a scope established by an earlier decorator; save the worker's old context.
4. **Always calling `set(captured)` even when null.** Call `remove()` when absent to avoid keeping a useless ThreadLocal entry.
5. **Passing a mutable reference instead of a snapshot.** Caller may modify the map/list after submission; the task reads inconsistent data.
6. **Using `InheritableThreadLocal` for thread pools.** Reused workers do not receive new snapshots per request and may retain old context.
7. **Passing raw `HttpServletRequest`, `Connection`, `EntityManager`, or transactions to workers.** They have their own scope/thread lifecycles and may be unsafe.
8. **Assuming TaskDecorator catches all exceptions on `submit`.** `FutureTask` can hold errors inside the Future; check `get()`/handlers.
9. **Assuming TaskDecorator applies to every executor in the app.** It only applies where configured; `@Async` and `CompletableFuture` may pick other executors.
10. **Believing `ContextPropagatingTaskDecorator` automatically knows every custom ThreadLocal.** Registered context accessors and proper dependencies are required.
11. **Testing only one request.** Leak bugs only surface when a worker is reused for another request or after a prior task throws.
12. **Copying just an ID into MDC and treating it as trace propagation.** Log correlation does not replace observation/span context.
13. **Letting snapshots hold unnecessary credentials/tokens.** Risks data leakage and prolonged retention in queues.
14. **Using a decorator to open a transaction and move resources to another worker.** Transactions must be designed on the actual executing thread, not by copying internal thread-locals.
15. **Ignoring cleanup when a task spawns nested async work.** Each boundary needs explicit propagation; parent cleanup does not directly clean up child tasks.
16. **Forgetting pool lifecycle.** Console demos need `initialize` and shutdown; container-managed Spring beans must not be shut down after every request.

## 16. Self-Check Questions

**Question 1.** Why does the caller's `ThreadLocal` usually not appear inside a task running on `ThreadPoolTaskExecutor`?  
**Answer:** ThreadLocal is bound to a thread, whereas a pool worker is a different thread. You must capture the value at submission and set it on the worker.

**Question 2.** Why should you restore `previous` instead of simply calling `remove()` after a task?  
**Answer:** The worker might already be inside an outer scope with a valid context. Restoring preserves that scope's contract; only remove when previous was null.

**Question 3.** If a task throws an exception, what must `TaskDecorator` still do?  
**Answer:** Run cleanup in `finally`. With `submit`, the error may reside in the Future rather than being thrown directly from the callback.

**Question 4.** Does using `ContextPropagatingTaskDecorator` automatically transfer a JDBC transaction from caller to worker?  
**Answer:** No. Imperative transactions and resources are thread-bound; you need a separate transactional boundary on the worker.

**Question 5.** Is testing task A and seeing the right request ID enough to conclude there is no leak?  
**Answer:** No. You must test B/C on the same worker, especially after a failing task, and inspect the previous worker context before setting up the new task.

**Question 6.** If a method uses `@Async("poolA")` while TaskDecorator is only attached to poolB, does it take effect?  
**Answer:** No, unless work is actually routed through poolB via another path. It must be attached to the exact executor receiving the task.

**Question 7.** If the caller changes the request ID after submitting, which ID should the worker see?  
**Answer:** The snapshot at `decorate`/submission time of that task, not the caller's newer value afterward.

**Key takeaway:** for every asynchronous task, **capture on caller → set on worker → run delegate → restore/clear in finally**. It is precisely the cleanup and restoration step on reused workers that makes propagation both useful and free from cross-request context mixing.

### References

- [Spring Framework — TaskDecorator JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/TaskDecorator.html)
- [Spring Framework — ThreadPoolTaskExecutor JavaDoc and setTaskDecorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Micrometer — Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
- [Java SE 17 — ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html)
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
