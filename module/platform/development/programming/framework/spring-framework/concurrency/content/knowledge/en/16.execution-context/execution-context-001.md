# ThreadLocal Does Not Automatically Follow Work to Another Thread Pool

## Objectives

In a Spring application, information about a single processing flow such as a correlation ID, request ID, acting account, or data for logging is often stored in a `ThreadLocal`. This is convenient when all calls happen **on the same thread**. However, `@Async`, `TaskExecutor`, `ExecutorService`, `CompletableFuture.supplyAsync(...)`, and several parallel processing mechanisms can hand off part of the work to **another thread**. When that happens, the sender thread's `ThreadLocal` **does not automatically appear** on the receiving thread.

This is an **execution context** issue, not a bug in `@Async`. Misunderstanding it can cause lost correlation IDs, logs that cannot be correlated to a request, reading the wrong user, or worse, **leaking context data from a previous task** when a thread pool reuses a worker.

This lesson helps you:

1. Accurately explain that `ThreadLocal` binds a value to a **thread**, not to a task, `Future`, HTTP request, or Spring bean.
2. Understand why `ThreadLocal.get()` can have a value on the caller yet return `null` on a worker running `@Async`.
3. Distinguish between `ThreadLocal`, `InheritableThreadLocal`, passing data via parameters, and intentional context propagation mechanisms.
4. Use Spring's `TaskDecorator` to **capture** context when submitting a task, **attach** it to the worker during execution, and **restore/clear** it in `finally`.
5. Run a Java 17+ program with Spring Framework 6.2.x demonstrating both context loss, intentional context propagation, and preventing leaks across a reused worker.
6. Identify contexts that **should not be blindly copied**, especially transactions, `EntityManager`, request-scoped objects, and mutable security state.

**Key takeaway:** `ThreadLocal` solves data access **for the current thread**. An executor solves execution **by task**. If you want to carry part of the context from caller to worker, you must design **context handoff** at the submission boundary and cleanup at the task completion boundary.

## 1. How Does ThreadLocal Store Data Per Thread?

`java.lang.ThreadLocal<T>` provides the basic APIs:

```java
ThreadLocal<String> requestId = new ThreadLocal<>();

requestId.set("req-123");
String sameThread = requestId.get(); // "req-123"
requestId.remove();                  // remove binding on the current thread
```

This is a simple Java snippet inside a method, not a standalone program. A shared `ThreadLocal` object does **not** mean threads share a single value. Each thread has its own binding for the same `ThreadLocal` key.

Model:

```text
                   THE SAME ThreadLocal<String> KEY
                                   |
      +----------------------------+----------------------------+
      |                            |                            |
  request-thread-1             pool-worker-1                pool-worker-2
  key -> "req-A"               key -> null                  key -> "req-old"
      |                            |                            |
  get() -> "req-A"             get() -> null                get() -> "req-old"
```

`new ThreadLocal<>()` has a default `initialValue()` of `null`; a thread that has never `set` that key will read `null`. If you use `ThreadLocal.withInitial(supplier)`, a thread can receive **its own initial value**, but that is still **not** a value automatically copied from the caller.

A `static final ThreadLocal<String> ID` variable is usually a **shared key** referenced by all threads. The value still lives in each thread's private storage area. Do not confuse `static` on the key with `static String currentRequestId` (a shared value variable, which is unsafe if concurrent requests overwrite it).

### ThreadLocal Is Not a Data Store for a Request

An HTTP request is sometimes handled entirely by a single Servlet thread, so operations on that same thread read the corresponding `ThreadLocal`. However, when a request is dispatched to a worker, handed off to a callback, scheduled for retry, or involved in asynchronous processing, preserving request identity **is no longer guaranteed by a plain ThreadLocal**. It is also unsuitable for storing long-lived business results or sharing state across processes.

## 2. Why Doesn't @Async Automatically Carry ThreadLocal to the Worker?

Imagine code in a controller/service:

```java
ContextHolder.TRACE_ID.set("trace-A");

CompletableFuture<String> answer = service.runAsync();
```

This is a snippet illustrating behavior; `ContextHolder`, `service`, Spring infrastructure, and imports are defined in the complete program later on.

If `service` is a Spring bean with an `@Async("workerExecutor")` method, the call through the proxy is typically submitted to the executor:

```text
CALLER THREAD                            WORKER THREAD
--------------------------------        --------------------------------
TRACE_ID.set("trace-A")
TRACE_ID.get() == "trace-A"

call service.runAsync()
    |
    +-- Spring async proxy
    +-- executor.submit(task) ----------> worker receives task
                                         TRACE_ID.get() == null (*)
                                         runs body of runAsync()
    |
    +-- caller receives Future
    |
caller still keeps "trace-A"             worker has its own ThreadLocal map

(*) Assumes the worker has not been bound a value for that key and ThreadLocal
    does not have a custom initialValue.
```

`@Async` primarily dispatches **a method call** to an executor. It does not automatically copy all thread-local variables, HTTP session state, or transactions from the caller. Depending on the framework, certain context types have specialized wrappers/propagation, but you **must not assume** that every ThreadLocal is carried over.

Furthermore, if `@Async` does not activate due to missing `@EnableAsync` or self-invocation `this.runAsync()`, the method body may execute directly on the caller. In that case `ThreadLocal.get()` sees the caller's value, but **that is not proof of successful propagation**: in reality, no thread switch may have occurred at all.

### Distinguishing Java `Executor` and Spring `@Async`

- `Executor.execute(...)` accepts a `Runnable` and executes it according to the executor's policy. Some executors run directly on the caller (`Runnable::run`), while others use a pool.
- `ExecutorService.submit(...)` typically returns a `Future`, but `Future` **does not carry** the submitting thread's `ThreadLocal` by contract.
- `@Async` in Spring uses a proxy/interceptor to submit the call to an executor and then returns a completion handle; per-thread data rules remain the same as the JDK.
- `CompletableFuture.supplyAsync(...)` schedules the task on the JDK's default executor or a passed executor. The supplier may run on a thread that lacks the caller's `ThreadLocal`.
- With callbacks `thenApply`, `whenComplete`, `handle`, the callback code may run on the thread that completes the stage or the thread that registers the callback if the stage is already complete. A callback's context must be determined by the actual executing thread, **not** by the thread that originally created the future.

## 3. Risks in a Thread Pool: Missing Context and Leaking Old Context

A thread pool **reuses** workers for many tasks:

```text
Request A:
  submit Task A -> worker-1
  Task A: TRACE_ID.set("A")
  Task A: forgets remove()

Request B:
  submit Task B -> worker-1
  Task B: TRACE_ID.get() -> "A"  !!! if not reset

Request C:
  submit Task C -> worker-1
  Task C: may see the value left behind by B
```

If a task sets a value and forgets to clean up, the state persists on the worker until it is cleared/replaced or the thread terminates. In a long-lived server, this is a hard-to-detect bug: user B's logs can carry A's trace ID; with security information, the consequences are even more severe.

Two symmetrical problems:

1. **Missing the right data**: caller has `"B"` but the worker has `null` because it was not propagated.
2. **Having the wrong data**: worker retains `"A"` from an old task because it was not cleaned up, and Task B mistakenly reads it.

A proper propagation mechanism must handle **both**: establishing the right snapshot for the current task, even when the snapshot is `null`, and restoring the worker's previous state after the task.

You should not merely write:

```java
executor.execute(() -> {
    TRACE_ID.set(captured);
    doWork();
});
```

This is an example lacking cleanup, not a pattern to follow. If `doWork()` throws an exception, the worker still retains the binding. If `captured` is null and we want to clear the binding, calling `set(null)` does not clearly express removal semantics, and also causes issues when `ThreadLocal.withInitial` needs re-initialization. Good practice is to use `try/finally`.

## 4. Can InheritableThreadLocal Save You?

`InheritableThreadLocal<T>` is a subclass of `ThreadLocal<T>`: when **creating a new child thread**, the runtime can give that thread an **inherited initial value** from the parent at thread creation time. This is not a "copy on every task submission" mechanism.

Pure Java 17 example:

```java
InheritableThreadLocal<String> inherited = new InheritableThreadLocal<>();
inherited.set("parent-A");

Thread child = new Thread(() ->
    System.out.println(inherited.get())
);
child.start();
child.join();
inherited.remove();
```

Placed inside a method that handles `InterruptedException`, running this successfully prints:

```text
parent-A
```

Why is this approach **unsuitable for propagating request context across a thread pool**?

- A pool worker may have been created long **before** the new request, so it does not receive updated values from the submitting thread.
- If a worker happens to be created while request A is active, it can inherit `"A"` and **keep that value** for requests B/C unless the application performs proper cleanup.
- Whether to create a new thread or reuse an existing one is the executor's decision. You should not design context correctness around this non-deterministic timing.
- With mutable objects, inheritance may copy a **reference**, not necessarily a deep copy; concurrent modifications across threads can cause races/data leaks.
- Some thread factories may choose not to inherit inheritable thread locals. You should not rely on a universal assumption when code runs inside a container or worker-managing library.

Therefore, **do not** replace `ThreadLocal` with `InheritableThreadLocal` as a quick fix for `@Async` or pools. Correctness must rely on propagation at **task submission**, not at **thread construction**.

## 5. Explicit Parameter Passing Is Usually the Safest Choice

If the required data is known on the caller, the easiest-to-understand approach is to pass it as a parameter or an immutable request context:

```java
public record JobContext(String correlationId, String tenantId) {}

@Async("workerExecutor")
public CompletableFuture<String> process(JobContext context, String payload) {
    return CompletableFuture.completedFuture(
        context.correlationId() + ":" + payload
    );
}
```

This is a snippet of a Spring bean; it requires `@EnableAsync`, a `workerExecutor` bean, imports, and invocation through a proxy. It is not a standalone file.

**Advantages:** No hidden state needed, you can directly read the exact information the task receives, easy to test, and well-suited for work that outlives a request or goes through a message queue. If a task runs after the caller's request ends, the required information still lives inside the intentionally passed DTO.

**Note:** Pass only the necessary data; do not pass references to an HTTP request object, mutable security internals, transaction-bound resources, or a JPA `EntityManager` to a worker. When a record's field is a mutable object, the record **does not automatically provide deep immutability**. You must consider copying/ownership.

`ThreadLocal` remains useful for logging/tracing APIs that use per-thread context where we cannot add parameters to every method. In such cases, design a clear bridge via `TaskDecorator` or an equivalent wrapper.

## 6. TaskDecorator: Capture on Submit, Bind on Run, Clean Up on Exit

Spring provides `org.springframework.core.task.TaskDecorator`, an interface used to wrap a `Runnable` **before the executor runs it**. `ThreadPoolTaskExecutor` has a `setTaskDecorator(...)` setter. Its primary purpose is to attach execution context or monitor execution.

Safe pattern for a `ThreadLocal<String>`:

```java
executor.setTaskDecorator(task -> {
    String captured = ContextHolder.TRACE_ID.get(); // on submitting thread
    return () -> {
        String previous = ContextHolder.TRACE_ID.get(); // on worker
        try {
            if (captured == null) {
                ContextHolder.TRACE_ID.remove();
            } else {
                ContextHolder.TRACE_ID.set(captured);
            }

            task.run();
        } finally {
            // Restore the worker's state, even if the task fails.
            if (previous == null) {
                ContextHolder.TRACE_ID.remove();
            } else {
                ContextHolder.TRACE_ID.set(previous);
            }
        }
    };
});
```

This is a configuration snippet inside a method that has `ThreadPoolTaskExecutor executor` and `ContextHolder`, not a standalone Java file. The complete code in the next section uses this exact principle.

### Point-by-Point Explanation

1. **When the decorator is called on the submitting thread:** `captured` is a snapshot of the value to be propagated. If the caller changes `ThreadLocal` right after submitting, the task still uses the earlier snapshot.
2. **When the wrapper runs on the worker:** `previous` saves the **worker's** old binding, not the caller's. This ensures proper handling when wrappers are nested or when the executor had a valid prior context.
3. **Before `task.run()`:** set the captured value, or remove it when the caller had no context. That way, task B never sees the value left by A.
4. **Inside `finally`:** always restore the worker's state before the wrapper ran. Independent of success or exception.
5. **Does not modify the caller:** the binding and cleanup code only runs on the worker. The caller remains responsible for cleaning up its own `ThreadLocal` when the request finishes.
6. **Does not automatically add workers or retry:** the decorator only wraps the callback; it does not alter queue/thread/rejection policies and does not handle business errors on its own.

If you want `TaskDecorator` to always leave the worker clean even when an unexpected `previous` value exists, you must decide ownership and requirements from other frameworks. In a potentially nested callback-wrapping model, **restoring the previous value** is the least destructive approach to outer layers' context. However, stale garbage state already present before the decorator runs must be fixed at its source; you cannot use "restoring previous" as a cure for an existing leak.

**Important when using `submit` / `Future`:** `TaskDecorator` may be invoked on a callback wrapper such as `FutureTask`, rather than directly on the user's `Runnable`. An error from the computation may be held inside `FutureTask` and **not thrown** from the decorator's `Runnable.run()`. Therefore, a `try/catch` around `task.run()` inside a decorator **is not** a complete mechanism for observing task failures. Use `Future`, completion callbacks, `AsyncUncaughtExceptionHandler`, or logging/metrics with clear contracts.

## 7. Complete Java 17+ and Spring Framework 6.2 Example

The example performs three verifications:

- **Without propagation:** the caller has trace `"req-A"`, the `@Async("plainExecutor")` call uses its own worker and sees `null`.
- **With propagation:** `@Async("contextExecutor")` runs the same kind of work, but `TaskDecorator` captures `"req-A"` and binds it on the worker; the worker reads it accurately.
- **No leak across reuse:** the caller changes context to `"req-B"`, then clears the context; a single worker of `contextExecutor` is used **three times**, sequentially seeing `"req-A"`, `"req-B"`, and `null`, without retaining old values.

We use a fixed single worker per pool and `Future.get(...)` to guarantee observation order. We do not rely on `Thread.sleep()` or timing races between workers.

### Directory Structure

```text
threadlocal-propagation-demo/
├── pom.xml
└── src/main/java/example/ThreadLocalPropagationDemo.java
```

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>threadlocal-propagation-demo</artifactId>
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
                    <mainClass>example.ThreadLocalPropagationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Create `src/main/java/example/ThreadLocalPropagationDemo.java`:

```java
package example;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class ThreadLocalPropagationDemo {

    // Only the key is shared; each thread holds its own value.
    public static class TraceContext {
        static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();
    }

    public record Reading(String traceId, String threadName) {
    }

    public static class WorkService {
        @Async("plainExecutor")
        public CompletableFuture<Reading> plainRead() {
            return CompletableFuture.completedFuture(
                new Reading(
                    TraceContext.TRACE_ID.get(),
                    Thread.currentThread().getName()
                )
            );
        }

        @Async("contextExecutor")
        public CompletableFuture<Reading> decoratedRead() {
            return CompletableFuture.completedFuture(
                new Reading(
                    TraceContext.TRACE_ID.get(),
                    Thread.currentThread().getName()
                )
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {
        @Bean
        public WorkService workService() {
            return new WorkService();
        }

        @Bean("plainExecutor")
        public ThreadPoolTaskExecutor plainExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(4);
            pool.setThreadNamePrefix("plain-");
            return pool;
        }

        @Bean("contextExecutor")
        public ThreadPoolTaskExecutor contextExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(4);
            pool.setThreadNamePrefix("ctx-");

            pool.setTaskDecorator(task -> {
                // Capture context from the thread submitting the task.
                String captured = TraceContext.TRACE_ID.get();

                return () -> {
                    String previous = TraceContext.TRACE_ID.get();
                    try {
                        if (captured == null) {
                            TraceContext.TRACE_ID.remove();
                        } else {
                            TraceContext.TRACE_ID.set(captured);
                        }
                        task.run();
                    } finally {
                        if (previous == null) {
                            TraceContext.TRACE_ID.remove();
                        } else {
                            TraceContext.TRACE_ID.set(previous);
                        }
                    }
                };
            });

            return pool;
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            WorkService service = context.getBean(WorkService.class);

            // A simulated "request" sets ThreadLocal on the caller.
            TraceContext.TRACE_ID.set("req-A");
            try {
                Reading plain = service.plainRead()
                    .get(5, TimeUnit.SECONDS);
                Reading copiedA = service.decoratedRead()
                    .get(5, TimeUnit.SECONDS);

                // Another request passes through the same ctx worker.
                TraceContext.TRACE_ID.set("req-B");
                Reading copiedB = service.decoratedRead()
                    .get(5, TimeUnit.SECONDS);

                // Caller has no context; worker must not see
                // values from the previous two tasks.
                TraceContext.TRACE_ID.remove();
                Reading withoutContext = service.decoratedRead()
                    .get(5, TimeUnit.SECONDS);

                boolean reusedWorker =
                    copiedA.threadName().equals(copiedB.threadName())
                    && copiedB.threadName().equals(
                        withoutContext.threadName()
                    );

                System.out.println("plainMissing="
                    + (plain.traceId() == null));
                System.out.println("firstCopied=" + copiedA.traceId());
                System.out.println("secondCopied=" + copiedB.traceId());
                System.out.println("afterCallerClearMissing="
                    + (withoutContext.traceId() == null));
                System.out.println("plainPoolUsed="
                    + plain.threadName().startsWith("plain-"));
                System.out.println("contextPoolUsed="
                    + copiedA.threadName().startsWith("ctx-"));
                System.out.println("sameWorkerReused=" + reusedWorker);
                System.out.println("callerClean="
                    + (TraceContext.TRACE_ID.get() == null));
            } finally {
                // Caller thread must also clean up its own context.
                TraceContext.TRACE_ID.remove();
            }
        }
    }
}
```

Run in the `threadlocal-propagation-demo` directory with JDK 17+ and Maven:

```bash
mvn -q compile exec:java
```

Eight lines printed by the **program** in order, when run successfully:

```text
plainMissing=true
firstCopied=req-A
secondCopied=req-B
afterCallerClearMissing=true
plainPoolUsed=true
contextPoolUsed=true
sameWorkerReused=true
callerClean=true
```

### Why Are These Results Verifiable?

1. The Spring context creates the `WorkService` bean, two `ThreadPoolTaskExecutor` beans, and enables `@Async`. `WorkService` is a class without an interface and with public methods, so calls from `context.getBean(...)` are handled by the async proxy.
2. Main sets `"req-A"` on the **caller's ThreadLocal**, then calls `plainRead()`. `plainExecutor` has a `plain-...` worker; a **plain** ThreadLocal is not inherited from main, so `plain.traceId()` is `null`.
3. `decoratedRead()` is called under the same caller state. When the task is submitted, `contextExecutor`'s `TaskDecorator` captures `"req-A"`. The worker sets the snapshot, reads the value, and returns `Reading("req-A", "ctx-...")`.
4. Main waits for the result with `get` before changing the value to `"req-B"`. The second submission captures `"req-B"`, and reusing the worker does not lose the new snapshot.
5. Main calls `remove()` and submits a third time. The decorator captures the **absent value** (`null`), so the wrapper removes the binding before the task runs. The task reads `null`, not the old `req-B`.
6. Because each pool has `core=max=1` and tasks are awaited sequentially, the three decorated tasks use the same `contextExecutor` worker; the worker names match.
7. The thread names have distinct prefixes so both `plainPoolUsed` and `contextPoolUsed` checks yield `true`. The `finally` block cleans the caller even if an await call fails.
8. The `println` calls happen **after all futures have completed**, with no concurrent printing from workers, so stdout has a deterministic order.

If the environment fails to download dependencies or a task does not complete before `get(5, SECONDS)`, the program reports an error instead of printing all eight lines; that is an environment execution issue, not a change in ThreadLocal principles.

### Why Does the Demo Use a Custom ThreadLocal?

It allows observation independent of Spring Security, a servlet container, a logging framework, or request scope. If you used `SecurityContextHolder` or MDC, libraries might already have specialized wrappers or different context propagation configurations, making diagnosis more complicated. First understand **basic ThreadLocal**; then choose the specialized mechanism for each context type.

`TraceContext` in the demo only stores a dummy string, **not** secret tokens or access permissions. Do not use this single-string request ID propagation prototype to claim you have fully and safely propagated all security contexts in a real system.

## 8. Context Cleanup: Why Must We Use try/finally?

On a worker, an exception can occur at any moment:

```java
String old = TRACE_ID.get();
try {
    TRACE_ID.set(captured);
    runPossiblyFailingTask();
} finally {
    if (old == null) {
        TRACE_ID.remove();
    } else {
        TRACE_ID.set(old);
    }
}
```

This is a snippet requiring `TRACE_ID`, `captured`, and `runPossiblyFailingTask` to be defined in the method. Whether the task returns normally, throws a `RuntimeException`, or has a `return` path inside try, `finally` still executes in normal Java scenarios.

If a wrapper only calls `TRACE_ID.remove()` in finally and forgets to restore `old`, you may break the context of an outer wrapping layer on the same worker (e.g., nested decorators). If the wrapper only restores `old` when `old` was already stale data from a previous task, the source of the leak still needs fixing. The proper design rule is **each component is responsible for the binding it sets itself**, while the owner of the thread pool must have a policy to prevent stale context.

`ThreadLocal.remove()` is critical for long-lived thread pools because values remain attached to the thread until removed, replaced, or the thread terminates. For large data, forgetting cleanup causes both memory retention and the risk of accidentally exposing data between requests.

### Should You Pass a Mutable Object Directly?

No. If the caller captures a mutable reference and continues mutating it, the worker may observe inconsistent state. `TaskDecorator` capturing a **reference** does not automatically create a deep snapshot. Prefer passing small, immutable values or explicit copies. In particular, avoid letting a worker hold references to a request-scoped bean, an already completed HTTP request, or a data structure tied to another user.

## 9. Spring Security: Security Context Is a Separate Problem

Spring Security typically manages `SecurityContext` via `SecurityContextHolder` with a thread-bound strategy (by default usually using `ThreadLocal`). Therefore, an `@Async` method may see a **different** security context from the request thread.

In systems that need to carry authentication to a worker, Spring Security provides adapters such as:

- `DelegatingSecurityContextRunnable`
- `DelegatingSecurityContextCallable`
- `DelegatingSecurityContextAsyncTaskExecutor`

These types are designed to set up and clear `SecurityContext` around the callback according to Spring Security's contract. Read the API matching your project version and choose the proper context snapshot/ownership. Do not naively copy the entire `SecurityContextHolder`, do not retain user privileges after the request ends if business rules forbid it, and do not conclude that having a context automatically grants valid access rights at all times.

**Security is a trust boundary.** Propagating a correlation ID for logs is not the same as propagating authentication to authorize background tasks. For long-running tasks, you may need to re-authenticate or use a separately authorized service identity rather than carrying an HTTP request's security context.

## 10. MDC and Correlation ID for Logging

A common case is MDC (Mapped Diagnostic Context) of a logging framework. MDC is usually backed by thread-local storage, so logs inside `@Async` can lose the request ID unless propagation is configured.

Conceptual example using SLF4J MDC:

```java
Map<String, String> snapshot = MDC.getCopyOfContextMap();

return () -> {
    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        if (snapshot == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(snapshot);
        }

        delegate.run();
    } finally {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
};
```

This is a **non-standalone snippet**; it requires a logging implementation with MDC, `Map`, a `delegate` variable, and the decorator properly configured on the executor. The idea is the same as section 6, applied to the **entire MDC map**; check the MDC mechanism and copy semantics of the logging provider in use. Propagate only observability fields; do not put secrets, access tokens, sensitive information, or full request payloads into logs.

In systems using OpenTelemetry or Micrometer, tracing context has its own API and lifecycle; it is better to use verified instrumentations/context propagation rather than ad-hoc copying of multiple ThreadLocals.

## 11. Spring's ContextPropagatingTaskDecorator

Spring Framework provides `org.springframework.core.task.support.ContextPropagatingTaskDecorator`, which integrates with **Micrometer Context Propagation** to support certain execution contexts, such as tracing observations, when the environment has the appropriate library and context accessors.

Illustrative configuration example:

```java
@Bean("observedExecutor")
ThreadPoolTaskExecutor observedExecutor() {
    ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
    pool.setCorePoolSize(2);
    pool.setMaxPoolSize(4);
    pool.setQueueCapacity(16);
    pool.setThreadNamePrefix("observed-");
    pool.setTaskDecorator(
        new org.springframework.core.task.support.ContextPropagatingTaskDecorator()
    );
    return pool;
}
```

This is a non-standalone Spring configuration; it requires a supported Spring Framework version and the `io.micrometer:context-propagation` dependency along with the necessary context accessors. Installing the decorator **does not automatically guarantee that arbitrary ThreadLocals are copied**, and must not be assumed to safely copy transaction or security state just because the library is present.

Frameworks may have their own propagation mechanisms, and instrumentation adds overhead. Choose the exact set of contexts to propagate, benchmark if submitting many small tasks, and avoid double-propagation when multiple decorators/wrappers are applied together.

### Limitations of Automatic Propagation

- Only contexts captured by the configured mechanism travel with the task.
- A context may **expire** by the time the task starts (for example, the HTTP request has ended).
- Shared mutable objects can race regardless of how the reference is passed.
- Propagating a security context does not mean it is permitted to be used indefinitely.
- Do not capture transaction-bound resources for use on another thread.

## 12. Transaction, RequestContextHolder, and Request Scope

### Transaction Is a Thread-Bound Context

Spring's `@Transactional` typically uses `TransactionSynchronizationManager` to manage resources/transaction-bound data **on the executing thread**. If the caller opens a transaction and then calls an `@Async` method, the worker **does not automatically join the caller's transaction** merely because of an annotation or a decorator propagating some ThreadLocals.

```text
Caller thread                             @Async worker
--------------------------------         --------------------------------
@Transactional method
  transaction A / connection A
  |
  +-- submit async task ----------------> method runs on another thread
                                          does not automatically have transaction A
  |
  +-- caller commits/rolls back A
```

Do not try to "propagate a transaction" by copying internal ThreadLocals or sharing a JDBC `Connection`/JPA `EntityManager` to a worker. That breaks resource lifecycle and thread-safety assumptions. If a background task needs a transaction, **open a separate transaction boundary on the worker** using appropriate Spring bean/proxy structure and understand the advice ordering of `@Async`/`@Transactional`.

### Request-Scoped Objects May Not Exist on the Worker

`RequestContextHolder` binds request attributes to the thread. An `@Async` task may run after the HTTP request finishes, and the worker is not automatically placed into a valid request context simply from an old reference.

Inheritable request attribute mechanisms can be dangerous with thread pools: a worker can outlive the request and be reused for another user. Do not blindly pass `HttpServletRequest`, session objects, or request-scoped proxies to a worker; extract the required immutable data before submitting, or design the task to accept an explicit DTO.

### HTTP Async Does Not Mean ThreadLocal Propagates Automatically

Spring MVC has its own asynchronous HTTP processing contracts. Even when using an `@Async` service, the request thread can be blocked if the caller immediately calls `get()`/`join()`. With `DeferredResult`, `Callable`, or other asynchronous response forms, you must inspect context propagation at **each layer**: servlet dispatch, executor, completion callback, and response rendering. Do not treat async HTTP as a single continuous thread preserving the same ThreadLocal.

## 13. Call Order, Callbacks, and Nested Async

An async task can submit further tasks:

```java
CompletableFuture<Result> stage2 =
    stage1.thenApplyAsync(value -> transform(value), anotherExecutor);
```

This is a snippet inside a method with variables and types `Result`/`transform`; it is not a standalone program. The callback runs according to `anotherExecutor`'s policy, so the context it sees depends on the thread executing **stage2 itself**.

Even if the first task had its trace ID propagated by a decorator, a `thenApplyAsync` step sent to the common pool or another executor **without a decorator** can still lose context. With a non-async `thenApply` callback, the callback may run on the thread that completed the previous stage or the thread registering the callback if the previous stage is already done. Do not build code expecting a callback to always have a particular ThreadLocal unless you control the thread boundaries.

When there are multiple executors or stages sent across a message broker, the better choice is usually to **pass context metadata via parameters or message headers**. `TaskDecorator` only covers tasks going through the executor where the decorator is attached, not an entire pipeline spanning multiple systems.

## 14. Table of Common Misconceptions

| Misconception | Why It Is Wrong | What to Do Instead? |
| --- | --- | --- |
| “ThreadLocal is a shared variable for all tasks.” | Values are bound to the thread, not the task. | Pass context as a parameter or wrap at submission. |
| “@Async automatically carries all ThreadLocals from the caller.” | Async proxy picks an executor; it does not clone all thread state by default. | Use `TaskDecorator` or an appropriate wrapper. |
| “Worker reading `null` proves @Async is broken.” | That is standard ThreadLocal behavior on another thread. | Check thread/qualifier and dedicated propagation. |
| “Switching to InheritableThreadLocal is enough.” | Inherits at thread creation, not on every pool task submission. | Snapshot at task submission. |
| “A thread pool always creates a new worker for a new task.” | Workers are typically reused long-term. | Clean up bindings in `finally`. |
| “Previous task sets it and the next task overwrites it anyway.” | Next task may not set it, or an exception occurs before setting. | Clear for absent snapshots and restore in finally. |
| “Using `set(null)` is always equivalent to `remove()`.” | Binding still exists; `withInitial` behaves differently when read after remove. | Use `remove()` to delete the binding per contract. |
| “Decorator will catch every exception with try/catch.” | FutureTask can hold the exception inside `Future`. | Observe Future/completion or a separate async handler. |
| “Having a security context means it can be used forever.” | Privileges have their own lifecycle, scope, and validity. | Use dedicated Spring Security mechanisms and control authorization. |
| “@Transactional on caller means worker shares the transaction.” | Transaction-bound resources are thread-bound. | Open the worker's own transaction; do not copy bindings. |
| “Tracing's TaskDecorator copies every ThreadLocal.” | Only contexts registered for capture can propagate. | Configure context accessors and test each type. |
| “After @Async, all callbacks use the same worker.” | CompletableFuture has its own executor rules. | Explicitly specify the executor at each async branch. |
| “Keeping request results in ThreadLocal is a form of caching.” | Worker reuse can retain the wrong data and memory. | Use request/task-scoped state or a cache with its own lifecycle. |
| “When a request ends, all worker bindings disappear.” | Workers outlive requests and can retain bindings. | Clean up both caller and worker; do not hold request objects. |

## 15. Checklist When Reviewing an @Async Path

1. **Which contexts are needed?** Trace ID, tenant ID, MDC, SecurityContext, locale, request metadata, or transaction? Do not lump them all into one group with the same strategy.
2. **Who owns the value?** The current caller request, the user, or a long-running job? Can it expire before the task runs?
3. **Where is the submission point?** Is it the right bean/executor with `TaskDecorator` attached, or does the task go to another pool/common pool?
4. **When is it captured?** Is the snapshot taken before the caller cleans up its ThreadLocal? Is it a `String`/immutable DTO or a mutable object?
5. **When is it set on the worker?** The wrapper must set it before `task.run()`, including the null snapshot case.
6. **How is cleanup done?** Is there a `finally` to restore/remove, even if the callback throws an error or is interrupted?
7. **Does the caller clean up itself?** The worker decorator does not clear ThreadLocal on the request thread; the servlet filter/interceptor must manage its own lifecycle.
8. **Is InheritableThreadLocal being misused?** Does the pool have reused workers and risk inheriting stale context when creating workers?
9. **Which contexts cannot be copied?** Transactions/JDBC connections, EntityManager, HttpServletRequest, mutable authentication state, security secrets.
10. **Are there multiple async stages?** `thenApplyAsync`, `@Scheduled`, `@EventListener`, messaging, or other publishers must be reviewed separately.
11. **Is error observation right?** `TaskDecorator` is not complete error handling; Future/CompletableFuture has its own result/error semantics.
12. **Has it been tested concurrently?** Create Request A/B, a small worker pool, verify no lost context and no leaks; also test exceptions, cancellation, and shutdown.

## 16. Self-Check Exercises

**Question 1.** Thread A calls `TRACE_ID.set("A")`, then submits a task to a `ThreadPoolTaskExecutor` worker. Will the worker read `"A"` by default?

**Answer:** No. Standard `ThreadLocal` stores values per thread; the worker only sees its own binding (usually null if not set). `@Async` does not automatically clone bindings.

**Question 2.** Why doesn't `InheritableThreadLocal` reliably solve propagation across a thread pool?

**Answer:** It inherits when **a new thread is created**, whereas a pool can reuse a worker to run many tasks from different callers. The worker does not receive a new snapshot per submit, and can even retain an old context.

**Question 3.** In the example, why are `firstCopied=req-A`, `secondCopied=req-B`, yet `afterCallerClearMissing=true` even though the same worker is reused?

**Answer:** The decorator captures a snapshot on each submit, sets/removes accordingly before `task.run()`, and then restores the worker in finally. The next task does not see the previous binding.

**Question 4.** If `task.run()` throws an exception, when does the decorator's `finally` run?

**Answer:** Upon exiting the try block per Java rules, even on an exception; the wrapper restores/removes the context before the worker picks up the next task. However, a `FutureTask` can hold the exception inside the Future, so the decorator does not necessarily observe the error via catch.

**Question 5.** Should we copy `TransactionSynchronizationManager` or a JDBC connection from caller to worker?

**Answer:** No. Transactions/resources are not automatically safe across threads; you need a separate transaction boundary on the worker, not copying internal ThreadLocals.

**Question 6.** A `thenApplyAsync` callback is submitted to another executor without a decorator. Is it guaranteed to see the trace ID from the previous task?

**Answer:** No. Each submit/thread boundary requires its own propagation mechanism; the trace ID does not automatically move between pools.

**Question 7.** Does `ThreadLocal.withInitial(() -> "default")` automatically copy the caller's value to the worker?

**Answer:** No. The supplier initializes a value for **the thread calling `get`** when no binding exists; it does not copy a value from another thread.

**Question 8.** Does the caller calling `remove()` after submitting cause the task to lose the snapshot captured by `TaskDecorator`?

**Answer:** If the snapshot is an independent immutable value like `String`, no. The wrapper already holds the value at submit time. If the snapshot is a mutable reference, mutating the object's internal state can still affect the worker.

**Question 9.** An `@Async` method sees the caller's `ThreadLocal` because it is running on the caller. Does that confirm propagation works properly?

**Answer:** No. `@Async` might not be enabled, self-invocation might bypass the proxy, or the executor might run directly. You must verify the worker thread and proxy path before concluding.

### Key Takeaway

`ThreadLocal` binds a **value to a thread**, not **context to a task**. With Spring `@Async` and thread pools, a task can run on a different worker than the caller, and workers are reused. When propagation is needed, prefer passing immutable metadata via parameters; if an API requires thread-bound context, use `TaskDecorator` or a dedicated wrapper to **capture on caller → set on worker → run → restore/remove in finally**. Do not blindly propagate transaction/request/security state, and do not confuse log context with authorization.

### Official References

- [Java SE 17 — ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): per-thread bindings, `get`, `set`, `remove`, and `withInitial`.
- [Java SE 17 — InheritableThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InheritableThreadLocal.html): inheriting values at child thread creation time, not at pool submission time.
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): `@EnableAsync`, `@Async`, and executors.
- [Spring Framework 6.2.12 — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): `setTaskDecorator`, pool, queue, and lifecycle.
- [Spring Framework 6.2.12 — TaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/task/TaskDecorator.html): wrapping callbacks to set context and exception observation limitations.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html): `ContextPropagatingTaskDecorator` and Micrometer Context Propagation where appropriate.
