# Cleaning Up Context at the Right Time in Java Logging

## 1. Problem Statement

**Logging context** is the information attached to log events, such as `requestId`, `traceId`, `tenantId`, or `jobId`. It helps correlate records belonging to the same transaction without concatenating that information into every log message.

For example:

```text
INFO  requestId=REQ-A Start order
WARN  requestId=REQ-A Inventory low
INFO  requestId=REQ-B Start order
```

In Java logging libraries, context is typically managed through **MDC (Mapped Diagnostic Context)** in SLF4J/Logback or **ThreadContext** in Log4j2. Values are usually bound to the currently executing thread, rather than automatically belonging to an HTTP request unless the application actively manages the scope.

**Cleaning up context at the right time** means clearing or restoring those temporary values as soon as **the unit of work that owns them** finishes.

```text
Thread worker-1:
  Request A: put requestId=REQ-A
             log with REQ-A
             forgot to remove
  Request B: did not set requestId
             log is mistakenly tagged with REQ-A    <-- context leak bug
```

This is a serious log accuracy bug: dashboards may attribute an incident to the wrong request, wrong tenant, or mistake a payment failure from B for a failure from A. It can also cause sensitive data to be classified or stored under the wrong label.

**Rule of thumb:** whoever creates context must define **ownership scope**, **execution thread**, **async propagation**, and **cleanup on every exit path**.

### Lesson Objectives

After this lesson, you will know:

- When to use `remove`, `clear`, and **restore** the previous value.
- The difference between `SLF4J MDC.putCloseable` and `Log4j2 CloseableThreadContext`.
- How to set and clean up context in requests, message listeners, jobs, and thread pools.
- Why `ExecutorService` and `CompletableFuture` require capture/propagate/cleanup on the right thread.
- How to test two consecutive requests on the same worker using a Java 17 program.
- Common pitfalls with NDC stacks, async servlets, reactive code, security, and already-written log data.

## 2. Mechanism: MDC and ThreadContext

### SLF4J MDC

SLF4J provides the `org.slf4j.MDC` API:

```java
MDC.put("requestId", "REQ-A");
String id = MDC.get("requestId");
MDC.remove("requestId");
```

This is a snippet placed inside a method and requires `import org.slf4j.MDC;`. Each key/value is normally a string; the actual storage is determined by the **MDC adapter/provider**.

APIs to remember:

| SLF4J API | Effect |
| --- | --- |
| `MDC.put(key, value)` | Sets a value on the current context |
| `MDC.get(key)` | Retrieves a value |
| `MDC.remove(key)` | Removes a single key |
| `MDC.clear()` | Removes all current mappings |
| `MDC.getCopyOfContextMap()` | Returns a snapshot of the map; may be `null` |
| `MDC.setContextMap(map)` | Replaces the current map with the contents of the passed map |
| `MDC.putCloseable(key, value)` | Sets a key and returns an object that **removes the key** when closed |

SLF4J is a facade, so **having MDC in source code does not guarantee that logs contain the context**. The backend must support it, and the layout/encoder must output the corresponding keys.

### Log4j2 ThreadContext

Log4j2 provides `org.apache.logging.log4j.ThreadContext`:

```java
ThreadContext.put("requestId", "REQ-A");
String id = ThreadContext.get("requestId");
ThreadContext.remove("requestId");
```

Log4j2 supports two structures:

- **Map / MDC**: key-value pairs such as `requestId=REQ-A`, `tenantId=tenant-a`.
- **Stack / NDC**: nested sequence of operations, for example `checkout → payment → authorize`.

Cleanup operations must also match the structure: `ThreadContext.clearMap()` only clears the map; `ThreadContext.clearAll()` clears both the map **and the stack**. If a helper only owns the `operation` key, it should not call `clearAll()` because doing so can wipe out the caller's context.

### Why Are Thread Pools Dangerous?

Thread pools keep and reuse threads. A stale `ThreadLocal`/MDC map can outlive the request that owned it. Setting context on the main thread does not mean the worker thread has received that value; removing it on the main thread does not clean up the worker either.

```text
Caller thread (request A)
  MDC.put("requestId","REQ-A")
  submit(task)   ─────────────────► Worker thread
  MDC.remove("requestId")           task has its own context
                                    must set + clean up itself
```

**Behavior may depend on the backend and inheritance configuration**, but you should not rely on automatic thread context inheritance when using a pool, especially when workers are pre-created and reused over a long period.

## 3. Cleanup by Work Lifecycle

| Unit of Work | Set Context | Clean Up Context |
| --- | --- | --- |
| Synchronous HTTP request | After determining the request ID, before the handler processes it | In a `finally` block surrounding request processing |
| A message from a queue | When starting to process the message | After the final log of the message, whether success or error |
| Scheduled job | At the start of each job run | When the job finishes |
| A task in an executor | On the worker when the task starts | On the **same worker** in `finally` |
| A nested scope | Upon entering the sub-function | Upon exiting the sub-function, **restore** the parent context |
| Callback/reactive signal | Inside the callback scope that may run on another thread | When the callback finishes |
| Unit test | In test setup/scope | In `finally`/teardown, without affecting subsequent tests |

A common mistake is cleaning up too early:

```java
MDC.remove("requestId");
log.error("Request failed", exception);
```

At this point, the ERROR log line may no longer have the request ID. You should usually log at the boundary **while the context is still present**, then clean up in `finally`.

Conversely, if request A finishes without cleaning up before the thread serves request B, B's logs may carry `REQ-A`.

## 4. Basic Pattern: try/finally

**Unsafe:**

```java
MDC.put("requestId", requestId);
process();
MDC.remove("requestId");
```

If `process()` throws an exception, the remove statement is skipped.

**Safer when you own that key:**

```java
MDC.put("requestId", requestId);
try {
    process();
} finally {
    MDC.remove("requestId");
}
```

This is a snippet inside a method where the `requestId` variable and `process` method are provided, not a standalone Java file. `finally` executes when processing finishes normally, returns early, or throws an exception under normal Java control flow. It cannot be guaranteed to run if the JVM is forcibly killed or loses power.

When you need to log an exception:

```java
MDC.put("requestId", requestId);
try {
    process();
} catch (RuntimeException ex) {
    log.error("Request failed", ex);
    throw ex;
} finally {
    MDC.remove("requestId");
}
```

The ERROR log line is created **before cleanup**, so it can still be tagged with the right request ID; the `Throwable` is passed intact to the logger. Do not concatenate `ex.getMessage()` as plain text and drop the `Throwable` if the system needs the stack trace.

### Distinguishing remove and clear

`MDC.remove("requestId")` removes only one key; `MDC.clear()` clears the entire context map managed by the adapter on the current thread.

In a request filter that **owns the entire MDC of the thread**, calling clear at the boundary can be appropriate. However, a sub-library that only adds `operation` **must not arbitrarily clear everything**, because it could wipe out `traceId`, `tenantId`, or keys belonging to the caller.

## 5. SLF4J MDC.putCloseable: Auto-Removes but Does Not Auto-Restore

SLF4J provides a try-with-resources style scope:

```java
try (MDC.MDCCloseable ignored =
             MDC.putCloseable("requestId", "REQ-A")) {
    log.info("Processing");
}
```

After the scope exits, the `MDCCloseable` object **removes the `requestId` key**. This is the documented behavior in the SLF4J API.

**Trap when nesting scopes with the same key:**

```java
MDC.put("requestId", "REQ-PARENT");

try (MDC.MDCCloseable child =
             MDC.putCloseable("requestId", "REQ-CHILD")) {
    log.info("Child work");
}

log.info("Parent resumed");
```

After closing, `requestId` **does not automatically revert to `REQ-PARENT`**. `MDCCloseable.close()` removes the key rather than restoring the previous value.

Therefore:

- Use `putCloseable` when a scope owns a **new key** that did not exist before.
- If the key already exists and must be preserved, save the previous value first and restore it afterward.
- Do not assume all closeable APIs across frameworks have the same semantics.

## 6. Nested Scopes: Restoring the Caller's Context

Suppose a request already has `operation=checkout`, and a sub-step temporarily sets `operation=payment`. If you only remove it when done, the remaining logs of the request will lose `operation=checkout`.

**Safe pattern for a single SLF4J key:**

```java
String oldOperation = MDC.get("operation");

MDC.put("operation", "payment");
try {
    log.info("Payment step");
} finally {
    if (oldOperation == null) {
        MDC.remove("operation");
    } else {
        MDC.put("operation", oldOperation);
    }
}
```

This is a snippet where the `log` variable is already declared. If the key existed originally, the old value is restored; if it did not exist, the key is removed.

**When you need to temporarily replace the entire map:**

```java
Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.clear();
    MDC.put("requestId", "REQ-CHILD");
    doChildWork();
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
```

This snippet requires `java.util.Map` and the application's `doChildWork` method. `getCopyOfContextMap` returns a copy, which may be null; `setContextMap` replaces the entire map, so only use it when intentionally restoring a snapshot.

**Two ownership modes to distinguish clearly:**

1. **Top-level boundary:** owns the entire map of a request/job on a managed thread; can clear when finished.
2. **Borrowed scope:** a library/sub-function called when the caller already has context; must preserve or restore anything outside its own scope.

Using the wrong cleanup mode can cause two opposite bugs: leaving stale data from the old scope behind, or accidentally wiping out the parent scope's context.

## 7. Log4j2 CloseableThreadContext Has Restore Semantics

Log4j2 provides `CloseableThreadContext`, allowing temporary keys and stack elements to be set using try-with-resources:

```java
ThreadContext.put("operation", "checkout");

try (CloseableThreadContext.Instance ignored =
             CloseableThreadContext
                 .put("operation", "payment")
                 .put("requestId", "REQ-A")) {
    LOG.info("Inside payment");
}

// operation returns to "checkout";
// the new requestId is removed.
```

This is a snippet inside a class with `LOG` and imports from `org.apache.logging.log4j`.

**Unlike SLF4J's `MDC.putCloseable`**, `CloseableThreadContext.put` remembers the previous values of the keys modified by the scope and **restores them on close**. Newly added keys are removed; overwritten keys are reverted to their prior values.

Log4j2 also has a **stack/NDC**:

```java
try (CloseableThreadContext.Instance ignored =
             CloseableThreadContext
                 .put("requestId", "REQ-A")
                 .push("checkout")
                 .push("payment")) {
    LOG.info("Within nested operations");
}
```

Elements pushed within the scope are popped on close. If you use the `ThreadContext.push(...)` API directly, balance it with `pop()` in `finally`. If you only call `clearMap()`, NDC elements can still remain.

Only call `ThreadContext.clearAll()` at a boundary where the code genuinely **owns both the map and the stack**, not inside a helper that only manages a single key.

## 8. Java 17 Log4j2 Example: No Leaks Between Two Requests and a Worker

The program below runs two simulated requests `REQ-A` and `REQ-B`. Each request emits logs on the main thread and offloads part of its work to **a reused worker thread**. The context is captured at the submission point, installed on the worker, and restored after processing.

### 8.1. Project Structure

```text
context-cleanup-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── ContextCleanupDemo.java
        └── resources/
            └── log4j2.xml
```

### 8.2. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>context-cleanup-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-api</artifactId>
            <version>2.24.3</version>
        </dependency>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-core</artifactId>
            <version>2.24.3</version>
            <scope>runtime</scope>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

The versions are pinned so the example has an explicit configuration, not as a claim that these are the latest versions or suitable for every production environment. For real usage, check for security patches and keep `log4j-api`/`log4j-core` versions aligned.

### 8.3. File src/main/resources/log4j2.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="Console" target="SYSTEM_OUT">
            <PatternLayout pattern="%level|%X{requestId}|%msg%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="Console"/>
        </Root>
    </Loggers>
</Configuration>
```

`%X{requestId}` prints the value from the ThreadContext map. If the key is absent, the space between the two `|` characters is empty. This is a minimal pattern for the demo; production setups should include timestamp, logger name, thread, and exception details as appropriate.

### 8.4. File src/main/java/demo/ContextCleanupDemo.java

```java
package demo;

import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.apache.logging.log4j.CloseableThreadContext;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.apache.logging.log4j.ThreadContext;

public final class ContextCleanupDemo {
    private static final Logger LOG =
            LogManager.getLogger(ContextCleanupDemo.class);

    public static void main(String[] args) throws Exception {
        // Only do this at startup of a standalone demo program.
        ThreadContext.clearAll();

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            // Initialize the worker before the caller has a requestId.
            pool.submit(ThreadContext::clearAll).get();

            runRequest("REQ-A", pool);
            runRequest("REQ-B", pool);

            System.out.println(
                    "main-context=" + ThreadContext.get("requestId"));
            System.out.println("done");
        } finally {
            pool.shutdown();
            ThreadContext.clearAll();
        }
    }

    private static void runRequest(
            String requestId, ExecutorService pool) throws Exception {

        try (CloseableThreadContext.Instance ignored =
                     CloseableThreadContext.put("requestId", requestId)) {

            LOG.info("begin");

            // Snapshot at the caller, before submitting the task.
            Map<String, String> captured =
                    new HashMap<>(ThreadContext.getImmutableContext());

            Future<?> task = pool.submit(() -> {
                // Preserve any values the worker already had before the task.
                Map<String, String> oldWorker =
                        new HashMap<>(ThreadContext.getImmutableContext());

                ThreadContext.clearMap();
                try {
                    ThreadContext.putAll(captured);
                    LOG.info("worker");
                } finally {
                    // Clean up the task's context on the worker itself.
                    ThreadContext.clearMap();
                    ThreadContext.putAll(oldWorker);
                }
            });

            task.get();
            LOG.info("end");
        }

        // Scope exited: main's requestId must be gone.
        LOG.info("after scope");

        String workerAfter = pool.submit(
                () -> ThreadContext.get("requestId")).get();

        System.out.println(
                "main-after-" + requestId + "="
                        + ThreadContext.get("requestId"));
        System.out.println(
                "worker-after-" + requestId + "=" + workerAfter);
    }
}
```

### 8.5. Compiling and Running

Requires JDK 17+ and Maven, run from the `context-cleanup-demo` directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ContextCleanupDemo
```

**Lines produced by the application and Console appender**, excluding Maven/plugin-specific messages:

```text
INFO|REQ-A|begin
INFO|REQ-A|worker
INFO|REQ-A|end
INFO||after scope
main-after-REQ-A=null
worker-after-REQ-A=null
INFO|REQ-B|begin
INFO|REQ-B|worker
INFO|REQ-B|end
INFO||after scope
main-after-REQ-B=null
worker-after-REQ-B=null
main-context=null
done
```

The example uses `newSingleThreadExecutor()` and `Future.get()` so tasks execute in a verifiable order. The worker is initialized before the caller sets any context, and then reused for A and B. Thus the test demonstrates **real worker thread reuse**, rather than creating a new thread per request.

`ThreadContext.get(...)` returns `null` when a key is absent; Java string concatenation prints the literal text `null`. In real JSON logging, a missing field may be omitted or represented differently depending on the schema/encoder.

### 8.6. Why Is This Code Correct?

The **caller thread** uses `CloseableThreadContext.put`:

1. A opens the `REQ-A` scope.
2. The logger sees A on `begin` and `end`.
3. The scope closes and `requestId` is removed/restored.
4. The `after scope` log has no ID.
5. B opens a new scope and does not inherit `REQ-A`.

The **worker thread**:

1. Captures `oldWorker` before the task to preserve state that another caller/framework may own.
2. Clears the current map while installing the task's context.
3. Sets the `captured` snapshot taken from the caller.
4. Emits logs inside the task.
5. In `finally`, clears the task's context and restores `oldWorker`.
6. Subsequent tasks do not carry context A left behind by the previous task.

**Intentional limitation:** the example only manages the ThreadContext **map**. If an application uses the **NDC stack**, it must have a separate push/pop/restore policy. Snapshot/restore also cannot cure context that was already leaked **before the wrapper ran**; the worker's top-level boundary must still enforce its cleanup responsibility.

## 9. Anti-pattern: Cleaning Up on the Caller, Missing the Worker

Incorrect code:

```java
ThreadContext.put("requestId", "REQ-A");
pool.submit(() -> LOG.info("Do work"));
ThreadContext.remove("requestId");
```

This only removes the key on the **caller thread**, while the task runs on a worker with an independent context. It may not see `REQ-A` at all, or it may see another stale value.

Another incorrect snippet directly on the worker:

```java
pool.submit(() -> {
    ThreadContext.put("requestId", "REQ-A");
    LOG.info("Task A");
    // Forgot to remove/restore.
}).get();

pool.submit(() -> {
    LOG.info("Task B"); // May be mistakenly tagged with REQ-A.
}).get();
```

Both snippets assume `pool` and `LOG` already exist in the code; they are not standalone files. If the pool has only one thread, Task B may pick up the stale context.

**Fix:** capture on the submitting thread if propagation is needed; set the context and clean it up **inside the task's `try/finally`**. Do not treat calling `Future.get()` or `shutdown()` on the caller as a way to clear all ThreadLocals in workers.

## 10. CompletableFuture: Proper Cleanup on Continuations

`CompletableFuture.supplyAsync`, `thenApplyAsync`, and callbacks can run across multiple threads. An incorrect example:

```java
MDC.put("requestId", requestId);
try {
    return CompletableFuture.supplyAsync(this::loadData);
} finally {
    MDC.remove("requestId");
}
```

This in-method snippet may clear MDC on the caller **before the async task finishes**. It also **does not automatically propagate** context into the task running on the worker.

An SLF4J utility that captures and restores the context map:

```java
import java.util.Map;
import java.util.function.Supplier;
import org.slf4j.MDC;

static <T> Supplier<T> withMdc(Supplier<T> delegate) {
    Map<String, String> captured = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();

        try {
            if (captured == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(captured);
            }
            return delegate.get();
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    };
}
```

This is **illustrative utility code**: place the method in a Java class with a real `delegate` and full imports. `captured` is taken on the **caller when creating the wrapper**, while `previous` is taken **on the worker when the task starts**. After execution, the worker's context is restored even if the task throws an exception.

Usage:

```java
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(
                withMdc(() -> loadData()),
                executor);
```

`loadData` and `executor` are provided by the application. **Each continuation on a different thread** may need its own propagation scope. A wrapper on the initial future does not automatically spread context across all subsequent callbacks.

Additionally, `CompletableFuture` cancellation, timeouts, or errors may not stop a running task immediately. A `Future.get(timeout)` timing out on the caller **does not prove the worker task has exited and run cleanup**; you must verify task lifecycle, interruption handling, and `finally` blocks properly.

## 11. Servlets, Message Consumers, and Reactive Code

### Synchronous Servlet/Filter

A common pattern:

```java
String requestId = verifiedOrGeneratedRequestId();

MDC.put("requestId", requestId);
try {
    filterChain.doFilter(request, response);
} finally {
    MDC.remove("requestId");
}
```

This is **pseudo-code** for a servlet filter; it requires the Servlet API, request/response objects, and the project's ID generation method. A real filter must account for error/dispatch branches and clean up at the appropriate thread boundary.

**Do not unconditionally trust request ID headers from clients.** Values can be abnormally long, contain control characters, newlines, or spoofed strings; validate, normalize, or generate IDs on the server.

### Async Servlets

A filter may return after starting async processing while the request is not yet complete. Cleaning up context on the **filter thread** when it exits its scope is still correct; propagating the ID and cleaning up on the **async execution thread** must be handled by the task or framework integration. Keeping the filter thread's MDC alive until a callback completes would allow that thread to serve a new request with stale context.

### Message Consumers

Each message needs its own scope:

```java
for (Message message : batch) {
    MDC.put("messageId", message.id());
    try {
        handle(message);
    } finally {
        MDC.remove("messageId");
    }
}
```

This is an illustrative snippet, not a standalone Java file; `Message` and `handle` are defined by the application. If you only clear after the **entire batch**, message B could retain A's ID if B does not set all the same keys.

### Reactor/WebFlux

In a reactive pipeline, execution can hop between schedulers/threads. ThreadLocal-based MDC **is not a replacement for Reactor Context**. Use the context propagation mechanism supported by the framework, and set MDC only within the callback/signal scope that needs to log, restoring it immediately after the callback.

Do not copy the pattern of calling `MDC.put` before starting a subscription and calling `clear` when a future completes on some arbitrary thread. The subscribing thread, processing thread, and completion thread can all be different.

## 12. NDC Stacks and Nested Context

Log4j2 has a context stack:

```java
ThreadContext.push("checkout");
try {
    ThreadContext.push("payment");
    try {
        LOG.info("Authorizing");
    } finally {
        ThreadContext.pop();
    }
} finally {
    ThreadContext.pop();
}
```

This snippet lives inside a class with a Log4j2 `LOG`. Every `push` must be balanced by a `pop`, even when an exception is thrown. If forgotten, the stack can accumulate old operations on a reused thread.

You can prefer `CloseableThreadContext.push(...)` with try-with-resources to reduce the risk of forgetting to pop. Do not assume `ThreadContext.clearMap()` also clears the stack; if a boundary truly owns both, you can use `ThreadContext.clearAll()`.

With SLF4J, the MDC map is the standard concept; deque/stack APIs and actual support depend on the adapter. Do not assume Log4j2 NDC syntax works identically across every SLF4J backend.

## 13. AsyncAppender Is Not the Same as an Async Business Task

Two cases must be distinguished:

- **Async business task:** business code runs on another worker; the worker needs the right context **when creating the log event**.
- **Async logging:** the logger creates the event on the current thread, and the backend passes the event through a queue to an appender. The backend can **snapshot the context into the event** when the event is emitted.

Therefore, you do not need to keep `MDC` on the request thread until the file has finished flushing. What matters is that the context is accurate **at the moment the event is created** and cleaned up when the request/task scope ends. An event that has already snapshotted its context can continue being written after the caller's `ThreadLocal` has been cleaned up.

However, whether an event retains its context also depends on the backend, version, bridge, and encoder. If async logs are missing fields, inspect where the event is created, context propagation, snapshot policy, and layout; do not assume the cause is `MDC.remove` running too fast.

## 14. Testing with a Plain JDK 17 ThreadLocal

To observe thread reuse mechanics without downloading logging libraries, create `ThreadLocalCleanupDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class ThreadLocalCleanupDemo {
    private static final ThreadLocal<String> CONTEXT =
            new ThreadLocal<>();

    private static String task(String id) {
        CONTEXT.set(id);
        try {
            return CONTEXT.get();
        } finally {
            CONTEXT.remove();
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            System.out.println(
                    "A=" + pool.submit(() -> task("REQ-A")).get());
            System.out.println(
                    "after-A=" + pool.submit(CONTEXT::get).get());

            System.out.println(
                    "B=" + pool.submit(() -> task("REQ-B")).get());
            System.out.println(
                    "after-B=" + pool.submit(CONTEXT::get).get());
        } finally {
            pool.shutdown();
        }
    }
}
```

Run with JDK 17+:

```bash
javac ThreadLocalCleanupDemo.java
java ThreadLocalCleanupDemo
```

**Exact stdout:**

```text
A=REQ-A
after-A=null
B=REQ-B
after-B=null
```

This is a **simple ThreadLocal model for learning**, not the mandatory implementation of SLF4J MDC or Log4j2 ThreadContext. If you omit `CONTEXT.remove()`, the `after-A` and `after-B` tasks on the same worker can observe values left over from the previous task.

### Test Cases Needed in a Real Application

1. Request A succeeds; after the scope, no ID remains.
2. Request A throws an exception; `finally` still cleans up the context.
3. Request B runs on **the same worker** without an ID; logs do not contain `REQ-A`.
4. A nested scope changes a key and then restores the parent value.
5. A job running `CompletableFuture` has the right context on the worker.
6. A cancelled/timed-out task does not leak state when it eventually stops.
7. A `null` map snapshot does not cause helpers to throw `NullPointerException`.
8. The layout/JSON encoder outputs `requestId` when present and omits it properly when absent.
9. If using NDC, the stack does not grow after each request.
10. No sensitive keys or wrong tenant IDs appear in the next request's logs.

## 15. Security: Stale Context Does More Than Make Logs Hard to Read

A sample incident:

```text
Worker handles tenant A -> put tenantId=A -> forgot to clean up
Worker handles tenant B -> fails to set tenantId properly
Logs of B are tagged with tenantId=A
```

In observability systems, this data may be partitioned, searched, or access-controlled by tenant. Tagging the wrong tenant ID can mislead investigations and dashboards, or even leak operational information across customers.

**Principles:**

- Logging context is only **observability metadata**, not a source of truth for authentication/authorization.
- Never use `MDC.get("tenantId")` as an authorization mechanism.
- Never store passwords, cookies, API keys, tokens, card numbers, or sensitive PII in MDC.
- Validate/normalize IDs taken from clients; prevent newline/log injection and enforce length limits.
- Only propagate keys that are genuinely needed for async tasks.
- If another library owns the context, do not arbitrarily call `clear()`.
- Apply appropriate retention and access permissions to log files and collectors.

**Clearing context in the JVM does not erase data already written to files or sent to a collector.** Once an event has been emitted, protecting or deleting that data falls under separate storage, redaction, and retention policies.

## 16. Common Pitfalls

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| B carries A's `requestId` | Forgot cleanup on thread pool worker | Use `finally`/closeable in each task; test on the same worker |
| Caller has MDC but worker does not | Not captured/propagated on submit | Capture snapshot on caller, install when task runs |
| Cleaned up on main but worker still has ID | Two threads have separate state | Clean up on the worker itself |
| Helper wipes out caller's `traceId` | Called `MDC.clear()` on the whole map despite owning only one key | Remove only the key you own or restore a snapshot |
| Nested `MDC.putCloseable` loses parent value | SLF4J close removes the key instead of restoring | Save the old value and restore it manually |
| `CloseableThreadContext` does not auto-clean | Forgot to call close / didn't use try-with-resources | Scope properly and ensure close runs |
| NDC stack grows over time | `push` without matching `pop` | Use `finally` or a closeable scope |
| Async callback lacks context | Continuation runs on a different thread | Propagate/scope at each continuation that needs to log |
| Context still appears in async logs after clear | Event snapshotted context before cleanup | May be expected; distinguish the event from the current thread |
| Tests reuse a thread with an old ID | Didn't clear/restore in test teardown | Clean up at test boundaries |
| JSON logging missing `requestId` field | Layout/encoder doesn't output MDC or event logged before `put` | Check pattern and ordering |
| Future timed out but worker still logs | Caller stopping its wait doesn't mean the worker stopped | Design proper cancel/interrupt/cleanup on the worker |
| Logs attributed to wrong tenant | Stale MDC or untrusted client data | Clean up properly, validate IDs, never use MDC for auth |

### Debugging Checklist

1. Does the code call `SLF4J MDC` or `Log4j2 ThreadContext`?
2. Who owns the context and who cleans it up on **which thread**?
3. Is there a `try/finally` covering every throw/return branch?
4. Does any child scope overwrite an existing key?
5. Are there thread pools, callbacks, message consumers, or reactive schedulers?
6. Was the snapshot taken **before submitting**?
7. Did the worker **restore the previous context** or clear according to ownership?
8. Are the context map and stack handled separately when using NDC?
9. Does the `%X{requestId}` layout or JSON encoder output the required fields?
10. Run A then B **on the same worker** and verify no stale ID remains.

## 17. Knowledge Check

**Q1.** Why is cleanup needed even after an HTTP request has returned?  
**Answer:** The thread can be reused for another request; leftover MDC causes subsequent logs to be misattributed.

**Q2.** Why must `finally` be used?  
**Answer:** So cleanup is not skipped on early return or when an exception is thrown under normal Java control flow.

**Q3.** How do `MDC.remove` and `MDC.clear` differ?  
**Answer:** `remove` deletes a single key; `clear` deletes all mappings in the current context.

**Q4.** Does `MDC.putCloseable` restore an existing value?  
**Answer:** No. SLF4J's `close` removes the key. For nested keys, you must save and restore manually.

**Q5.** How is Log4j2's `CloseableThreadContext.put` different?  
**Answer:** On close, it restores previous values for overwritten keys and removes newly added keys.

**Q6.** Is setting MDC on the submitting thread enough for `ExecutorService`?  
**Answer:** No. You must have a proper context propagation mechanism and cleanup on the executing thread.

**Q7.** If a worker already had a leaked ID before a task ran, does snapshot/restore fix that leak?  
**Answer:** No. It restores the initial state, including a broken one; a reliable top-level boundary must clean it up.

**Q8.** Does `ThreadContext.clearMap` clear the NDC stack?  
**Answer:** No. The map and stack have separate lifecycles.

**Q9.** What happens if you remove MDC before logging the final exception?  
**Answer:** The ERROR event may lack the request/trace ID needed for investigation.

**Q10.** Why doesn't a future timeout guarantee the worker has cleaned up?  
**Answer:** A timeout only ends the caller's wait; the task may still be running.

**Q11.** Do you need to keep MDC until `AsyncAppender` finishes flushing?  
**Answer:** Not as a general rule. What matters is that the context is attached to the event when created and the backend handles snapshotting properly.

**Q12.** Can MDC replace the security context for tenant authorization?  
**Answer:** No. Logging context is only metadata for observability; permissions must be enforced by an independent authentication/authorization mechanism.

**Q13.** Does clearing MDC erase context fields already written to log files?  
**Answer:** No. Emitted events have their own lifecycle and storage policies.

**Key takeaway:** **Setting context is opening a scope; clearing or restoring it is closing that scope.** Do it properly on the **owning thread**, inside a **`finally`/closeable scope**, after the events that need the context have been created. With thread pools and async code, follow **capture → propagate → process → restore/cleanup**. SLF4J `MDC.putCloseable` removes keys on close; Log4j2 `CloseableThreadContext` restores previous keys. Avoid both stale context and accidentally wiping out the caller's data.

**Official References:**

- [SLF4J MDC API](https://www.slf4j.org/api/org/slf4j/MDC.html)
- [Log4j2 Thread Context](https://logging.apache.org/log4j/2.x/manual/thread-context.html)
- [Log4j2 CloseableThreadContext API](https://logging.apache.org/log4j/2.x/javadoc/log4j-api/org/apache/logging/log4j/CloseableThreadContext.html)
- [Logback Mapped Diagnostic Context](https://logback.qos.ch/manual/mdc.html)
