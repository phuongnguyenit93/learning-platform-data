# Avoiding Stale Context in Java Logging

**Stale logging context** occurs when metadata attached to a request, job, transaction, or trace **continues to appear in logs that no longer belong to that context**. For example, a thread finishes handling request A but still retains `requestId=req-A`; the thread pool reuses that same thread for request B, causing B's logs to be recorded with the wrong ID. In Java, this situation typically involves SLF4J/Logback's **MDC (Mapped Diagnostic Context)**, Log4j 2's **ThreadContext**, `ThreadLocal` wrappers, or inconsistent scope management.

The problem is not merely "hard-to-read" logs. Stale context can cause **misrouted tracing, inaccurate alerts, investigating the wrong customer, metadata leaks across requests/tenants**, or attributing events from one transaction to another. To prevent this, context must be managed according to its proper **lifecycle**, **set/restored/cleared with discipline**, and **propagated explicitly when switching execution contexts**.

This article focuses on preventing old context from being reused—not to be confused with field naming or JSON output. Examples use Java 17+, SLF4J/Logback, with equivalent notes for Log4j 2.

## 1. Which Contexts Easily Become Stale?

In application logs, context typically holds metadata that helps correlate events:

| Context field | Appropriate lifecycle | Risk if kept too long |
| --- | --- | --- |
| `requestId` | One HTTP request or equivalent unit of work | Request B's logs carry A's ID |
| `traceId` / `spanId` | The actually active trace/span | Correlating with the wrong trace/span, breaking trace alignment |
| `tenantId` | A request, job, or operation belonging to one tenant | Attributing tenant B's activity to tenant A |
| `jobId` | One job or one message processing run | A new job is logged under a finished job's ID |
| `orderId` / `paymentId` | A specific operation or individual event | Operations on another entity are misattributed |
| `retryAttempt` | A single attempt during a retry sequence | Post-retry events still carry the old attempt count |
| `userRole` | Verified security context within a request | Permissions/role misinterpreted when another user uses the thread |
| `operationName` | A small scope of a task | Logs outside the scope are tagged with a completed step's name |

Not every field belongs in MDC. `service`, `environment`, or `instanceId` are usually **resource metadata** that remain relatively stable for the entire process, making them suitable for attachment via logging/collector configuration. `durationMs`, `outcome`, and `errorCode` typically reflect **individual events**, not context that should persist across an entire request.

**Rule:** a field should only be kept within the scope where its value remains accurate. If a request processes multiple orders, `requestId` can stay the same, but `orderId` must change per operation or be emitted directly on each log event.

## 2. How Stale Context Forms

### 2.1. ThreadLocal and thread pools

Many MDC adapters store a key–value map per **current thread**. Thread pools reuse worker threads, whereas completing a request **does not necessarily destroy the thread**. Without cleanup, the old map remains for the next unit of work.

```text
Thread pool worker-1
    |
    | Request A: MDC.put("requestId", "req-A")
    | Log: requestId=req-A  event=request.started
    | Request A ends, forgets MDC.remove/clear
    |
    v
Same worker-1 handles request B
    | Request B fails to set requestId
    | Log: requestId=req-A  event=request.started  <-- WRONG
    |
    v
Request C continues reusing worker-1 ...
```

MDC is typically **per-thread data**, not a "JVM-wide global variable," but thread reuse makes the bug look like data bleeding across requests. Calling `MDC.clear()` on a **different thread** does not automatically clear the MDC of the worker holding the old data.

### 2.2. Exceptions or early returns bypassing cleanup

```java
// WRONG: illustrative snippet; MDC, LOG, and requestId already exist.
MDC.put("requestId", requestId);
LOG.info("event=request.started");
processRequest();  // May throw before the remove line below.
MDC.remove("requestId");
```

If `processRequest()` throws an exception, the `remove` line never runs. An early `return`, cancellation, or timeout in a branch causes the same bug when cleanup is not inside a `finally` block.

### 2.3. Nested scopes overwriting without restoring the previous value

For example, a request has `operationId=checkout-1`, and a subtask sets `operationId=payment-2`. If the subtask calls `MDC.remove("operationId")` when finished, the outer scope's context is lost as well. If it does not call `remove`, subsequent logs still carry `payment-2`. **Removing and restoring are not the same operation.**

### 2.4. Improper context propagation in asynchronous processing

The calling thread's MDC is not automatically present on a thread running `ExecutorService` or `CompletableFuture`. A common mistake is "grabbing" the worker thread's context when the task starts, at which point the worker may still hold stale context. Instead, you must **capture the valid context at submit time**, pass the snapshot into the task, and **restore the worker's previous state** after the task finishes.

### 2.5. Context changes while events are processed lazily

Logging can be processed asynchronously. If code relies on a shared mutable map and reads that map only at serialization time, an event from request A may end up tagged with metadata overwritten by request B. Proper logging frameworks usually snapshot event data; with custom wrappers/encoders, verify the **snapshot timing** rather than assuming every map object is immutable.

## 3. Operational and Security Consequences

| Symptom | What operators might misunderstand | Impact |
| --- | --- | --- |
| Log B carries `requestId=req-A` | Error B was caused by A | Investigating the wrong request |
| `traceId` retained from a prior task | Event belongs to a different distributed trace | Unable to link logs to the right span |
| Stale `tenantId` | Activity in tenant B belongs to tenant A | Risk of data and access confusion |
| `orderId` not reset | All steps processed the same order | Misreporting business flow |
| Worker lacks new context | Async events cannot be linked to caller request | Loss of correlation |
| MDC leak in a thread pool | One failure corrupts many subsequent requests | Cascading and hard-to-reproduce bugs |
| Oversized context or containing secrets | Logger/encoder and storage collect extra data | Resource waste, security risk |

**Stale context is a metadata correctness bug**, distinct from duplicate logs caused by appender additivity or choosing the wrong log level. The message text itself may still be business-accurate, but if the context is wrong, metadata-based queries and audits become unreliable.

## 4. The Most Important Principle: Scope + `finally`

Treat context like a resource with a lifecycle:

1. **Start scope:** identify the request/job/operation and validate the required IDs.
2. **Save the previous state** if nested scopes are possible.
3. **Set the exact context** for the current work.
4. **Execute business logic and log** within the scope.
5. **Restore or clear in `finally`**, even when an exception occurs.
6. **Do not use stale context to fill missing fields**; if a request has no trace, represent it as absent/null per schema instead of pulling a trace from the thread.

**SLF4J MDC** code pattern for a request's root scope:

```java
// Illustrative snippet: MDC, LOG, and requestId are already declared.
java.util.Map<String, String> previous =
        org.slf4j.MDC.getCopyOfContextMap();

try {
    // Request boundary: clear stale data that a pooled thread might hold.
    org.slf4j.MDC.clear();
    org.slf4j.MDC.put("requestId", requestId);
    LOG.info("event=request.started");
    processRequest();
} finally {
    if (previous == null) {
        org.slf4j.MDC.clear();
    } else {
        org.slf4j.MDC.setContextMap(previous);
    }
}
```

The snippet above **is not a standalone program**; in a real application, `LOG`, `requestId`, and `processRequest()` must exist. It illustrates a **root request scope** boundary: pre-scope context data is saved and restored, and the new request's context is explicitly established before emitting logs.

**Important note:** if `previous` already contained stale context due to an earlier bug, restoring all of `previous` can reintroduce stale data. At the server's request-entry boundary, have a policy to sanitize worker threads and detect unexpected context; snapshot restoration is only a good model for **valid nested scopes** or wrappers that do not own the full thread lifecycle. Never assume an old snapshot is "valid" if it was already wrong to begin with.

## 5. How `remove(key)`, `clear()`, and Restore Differ

| Operation | Meaning | When to use |
| --- | --- | --- |
| `MDC.put(key, value)` | Attaches/overwrites a value on the current thread. | Starting a scope or adding metadata |
| `MDC.remove(key)` | Removes one key from the current thread. | The scope truly owns that single key with no prior value to preserve |
| `MDC.clear()` | Clears the entire MDC on the current thread. | Request/job boundaries where the thread must start "clean" |
| `MDC.getCopyOfContextMap()` | Takes a snapshot of current key–value pairs. | Before changing scope or submitting an async task |
| `MDC.setContextMap(map)` | Sets the context map from a snapshot. | Restoring/installing a snapshot in a controlled scope |

**Do not call `clear()` arbitrarily in the middle of a valid request**, as it can wipe out `traceId`, `spanId`, or metadata held by the tracing framework. Conversely, calling only `remove("requestId")` may be insufficient if the request also attached `tenantId`, `userType`, or `operationId`. The choice must follow **who owns the context** and **which scope set those keys**.

SLF4J's MDC also provides `putCloseable(key, value)`. For example:

```java
// Illustrative snippet inside a method using SLF4J.
try (org.slf4j.MDC.MDCCloseable ignored =
             org.slf4j.MDC.putCloseable("operationId", operationId)) {
    LOG.info("event=operation.started");
}
```

`MDCCloseable` helps clean up a single key when closing the scope, but **does not automatically guarantee restoration of an overwritten prior value**. If nesting multiple scopes on the same key, use a helper that saves the previous value and restores it accurately; avoid assuming `close()` is equivalent to snapshot/restore.

## 6. Nested Context: Preserving Outer-Scope Fields

Suppose a request currently has:

```text
requestId=req-A
operationId=checkout
```

Upon entering a payment step, the code needs to temporarily set `operationId=payment`. After payment completes, `operationId` must return to `checkout` rather than disappearing completely or staying `payment`.

SLF4J pattern for **a single nested key**:

```java
// Illustrative code inside a method with LOG, paymentId, and business logic.
String before = org.slf4j.MDC.get("operationId");

try {
    org.slf4j.MDC.put("operationId", "payment");
    LOG.info("event=payment.started paymentId={}", paymentId);
    processPayment();
} finally {
    if (before == null) {
        org.slf4j.MDC.remove("operationId");
    } else {
        org.slf4j.MDC.put("operationId", before);
    }
}
```

This snippet **is not standalone**; the remaining variables/methods are provided by the application. Restoring the previous value ensures the caller's logger continues to see `operationId=checkout`.

For multiple keys, you can write a helper that creates a snapshot-based scope or use a framework's scoped API. Choose the right level of encapsulation: a helper that restores **all keys** might inadvertently overwrite context that was legitimately updated inside the scope; a helper that restores **a single key** is only suitable when the scope exclusively owns that key.

**Never leave an operation name or tenant permanently bound to a thread.** A thread is an execution mechanism; the request and operation are the semantic owners of context.

## 7. Thread Pools: Why Bugs Often Appear Randomly

Thread pools make bugs hard to reproduce because each request may run on a different thread. One day request B lands on a clean worker and behaves normally; another day it hits the exact worker that just handled request A and picks up stale context.

Intentionally broken example (**do not use in production**):

```java
// WRONG: executor and LOG already exist; requestId is taken from the request.
executor.execute(() -> {
    org.slf4j.MDC.put("requestId", requestId);
    LOG.info("event=task.started");
    processTask();
    // Forgot to clean up on success or exception.
});
```

If `executor` is a fixed or single-thread pool, subsequent tasks on that thread can continue seeing the old `requestId`.

**Correct approach:** in request-handling tasks, define the scope clearly and use `finally` to clean up/restore; in tasks dispatched to an executor, never assume the caller's MDC is automatically present. If there is no new context, the task must use its own appropriate context (e.g., `jobId`) or have no `requestId`.

### Does `InheritableThreadLocal` solve this?

Do not rely on `InheritableThreadLocal` to propagate MDC across a **thread pool**. Inheritance typically happens when a child thread is created, whereas pooled workers may have existed for a long time and served many requests. A new request's context at submit time is not automatically applied to an existing worker. Automatic inheritance can also carry unwanted data into unrelated threads.

With Java 21+ virtual threads, scope and propagation principles remain just as important; do not assume virtual threads make every MDC framework clean up or propagate context automatically. The runnable example in this article uses Java 17 and a standard `ExecutorService`.

## 8. Asynchronous Propagation: Capture at Submit, Apply in Task, Restore Afterward

General pattern:

```text
Request-receiving thread:
  context=req-A
  |
  +-- snapshot (req-A) at submit time
  |
  v
Executor worker:
  oldContext = worker's current snapshot
  setContext(req-A)
  try { run task, emit logs }
  finally { restore(oldContext) }

Caller:
  finally { end req-A scope }
```

If you capture context inside the worker **after the task has been queued and the caller has already cleaned up**, the snapshot may be empty or contain data from the worker's previous task. Capture it **when creating/submitting the task**, then pass a copy that shares no mutable state.

Wrapper pattern using SLF4J:

```java
// Illustrative code inside a class that has imported Map, Runnable, and MDC.
static Runnable withCapturedMdc(Runnable task) {
    java.util.Map<String, String> captured =
            org.slf4j.MDC.getCopyOfContextMap();

    return () -> {
        java.util.Map<String, String> workerBefore =
                org.slf4j.MDC.getCopyOfContextMap();
        try {
            if (captured == null) {
                org.slf4j.MDC.clear();
            } else {
                org.slf4j.MDC.setContextMap(captured);
            }
            task.run();
        } finally {
            if (workerBefore == null) {
                org.slf4j.MDC.clear();
            } else {
                org.slf4j.MDC.setContextMap(workerBefore);
            }
        }
    };
}
```

This is an **illustrative helper** that can be placed in a Java class with the appropriate SLF4J dependency. At the task boundary, decide whether restoring the worker's previous value is the desired behavior. In a generic wrapper, restoring is right so you don't break a caller/host's valid scope; in a worker dedicated to new requests, you may want to clear before and after while monitoring for unexpected state.

**Remember:** `captured` is held in the task's closure. If the queue backs up for a long time, the context can remain in memory until the task runs or is cancelled. Do not put tokens/secrets, heavy objects, or entire requests into context; keep only the necessary IDs/metadata and apply appropriate timeouts/cancellation.

## 9. Standalone Java 17 Example: Proving No Context Leaks Between Two Requests

This exercise uses **SLF4J 2.x + Logback Classic** to demonstrate actual MDC behavior in real logging rather than simulating it with a custom `ThreadLocal`. The program creates **an executor with only one worker thread** to force two requests to reuse the same thread; this way, the test catches stale context if the code forgets to clean up.

Each request has a clear lifecycle. An MDC snapshot is captured on the caller thread before task submission, installed on the worker, and then the worker's MDC is restored in `finally`. After the two requests, the program submits a task with no context to prove the worker does not retain `req-A` or `req-B`.

Use JDK 17 and Maven. The example pins `logback-classic:1.5.18`, **without claiming this is the latest version**. Production projects should choose a maintained, vulnerability-patched version compatible with their current SLF4J/JDK.

### 9.1. Directory structure

```text
stale-context-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── StaleContextDemo.java
        └── resources/
            └── logback.xml
```

### 9.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>stale-context-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.18</version>
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
                <configuration>
                    <mainClass>demo.StaleContextDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`logback-classic` pulls in the required Logback Core and SLF4J API dependencies via Maven. Do not add `slf4j-simple` or another SLF4J provider to the demo's runtime, as that can cause a provider conflict and prevent the Logback configuration from being selected.

### 9.3. src/main/resources/logback.xml

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level | requestId=%X{requestId:-none} | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

The pattern uses `%X{requestId:-none}` to print the `requestId` MDC key, or `none` when the key is absent. There is no timestamp or thread name in the pattern, making the sample output deterministic. This is a **text** configuration for the demo, not JSON structured logging; JSON output requires an appropriate encoder.

### 9.4. src/main/java/demo/StaleContextDemo.java

```java
package demo;

import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class StaleContextDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(StaleContextDemo.class);

    private static void restore(Map<String, String> snapshot) {
        if (snapshot == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(snapshot);
        }
    }

    // Use only at the root request boundary owned by the application.
    private static void withRequest(
            String requestId,
            Runnable action
    ) {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            MDC.clear();
            MDC.put("requestId", requestId);
            action.run();
        } finally {
            restore(previous);
        }
    }

    // Must be called on the thread holding the context before submitting.
    private static Runnable captureForWorker(Runnable action) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> before =
                    MDC.getCopyOfContextMap();
            try {
                restore(captured);
                action.run();
            } finally {
                restore(before);
            }
        };
    }

    private static void await(Future<?> task) {
        try {
            task.get();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Task interrupted", ex);
        } catch (ExecutionException ex) {
            throw new IllegalStateException("Task failed", ex);
        }
    }

    public static void main(String[] args) {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            withRequest("req-A", () -> {
                LOG.info("event=request.started");
                await(executor.submit(captureForWorker(
                        () -> LOG.info("event=work.completed")
                )));
            });

            withRequest("req-B", () -> {
                LOG.info("event=request.started");
                await(executor.submit(captureForWorker(
                        () -> LOG.info("event=work.completed")
                )));
            });

            // Third task does not receive any request context.
            await(executor.submit(
                    () -> LOG.info("event=worker.idle")
            ));
        } finally {
            executor.shutdown();
        }
    }
}
```

### 9.5. Compile and run

Open a terminal in the directory containing `pom.xml`; JDK 17 and Maven are required, and the first run may need network access to download dependencies:

```bash
mvn -q compile exec:java
```

**Log lines emitted by the program to stdout**, excluding Maven messages or environment warnings (if any):

```text
INFO | requestId=req-A | event=request.started
INFO | requestId=req-A | event=work.completed
INFO | requestId=req-B | event=request.started
INFO | requestId=req-B | event=work.completed
INFO | requestId=none | event=worker.idle
```

### 9.6. Output explanation and verification

1. `withRequest("req-A", ...)` establishes the request scope on the main thread, logs within the scope, and restores MDC in `finally`.
2. `captureForWorker(...)` is called **before `executor.submit(...)`**, i.e., on the main thread while MDC holds `req-A`. Request A's snapshot is applied to the worker while the task runs.
3. `await(Future.get())` forces task A to complete before request B starts. This ensures deterministic ordering in the example's output.
4. `captureForWorker` restores the worker's MDC in `finally`. Because the fresh worker initially had no context, it returns to having no `requestId` after task A.
5. Request B likewise passes a `req-B` snapshot, so the second `work.completed` event cannot mistakenly carry `req-A`.
6. `Executors.newSingleThreadExecutor()` reuses the exact same worker thread for both tasks. There is no automatic creation of a new thread per request that would mask a stale context bug.
7. The `worker.idle` task attaches no request context. It runs after both `Future.get()` calls, so the pattern prints `requestId=none`. This is concrete evidence that the worker did not retain the previous request's ID.
8. `executor.shutdown()` is called in `finally` to release resources for the demo. In long-lived services, executor and logging lifecycles are typically managed by the framework.
9. `restore(previous)` on the main thread and `restore(before)` on the worker are two independent actions. MDC is per-thread; cleaning up on the main thread **does not automatically clean up** the worker thread.

**What the demo does not cover:** in an HTTP framework application, tracing scope may already be managed by instrumentation; do not blindly wipe all context with `MDC.clear()` if other middleware owns keys like `traceId`. Integrate using the framework's official mechanisms and review who is responsible for cleanup. The example also does not intend to benchmark thread pool performance or guarantee logging durability.

## 10. Log4j 2 ThreadContext: Equivalent Principles

Log4j 2 uses `org.apache.logging.log4j.ThreadContext` to hold a context map/stack bound to the execution context:

```java
// Illustrative code; LOG and requestId are already declared.
org.apache.logging.log4j.ThreadContext.put(
        "requestId", requestId
);
try {
    LOG.info("event=request.started");
    processRequest();
} finally {
    org.apache.logging.log4j.ThreadContext.remove("requestId");
}
```

This code **is not standalone**. For nested scopes, you must save the old value before overwriting and restore it afterward, rather than simply removing it. Similarly, with an Executor, pass a **context snapshot** across the task boundary using Log4j 2's API or your framework's context propagation mechanism, then restore/clear in `finally`.

Log4j 2 offers context APIs and scoping features depending on the version; do not assume exact SLF4J MDC behavior across every Log4j 2 backend configuration without verifying. If using SLF4J as a facade and Log4j 2 as the backend, check the provider/bridge and actual context propagation path.

For Log4j 2's context stack, push/pop discipline must be balanced; a missing pop can leave values from a previous operation on the stack. Do not push context onto the stack without knowing which scope is responsible for popping it.

## 11. HTTP Filters, Interceptors, and Context Ownership

In web applications, the appropriate boundary to initialize `requestId` is usually a **filter/interceptor/middleware**. Instead of calling `MDC.put(...)` in every controller and hoping it gets cleaned up, design it like this:

```text
Request enters
  |
  +-- validate / issue requestId
  +-- establish request/tracing scope
  |
  v
Controller -> Service -> Repository
  |
  +-- submit async tasks with explicit context propagation
  |
  v
finally:
  close scope / restore or clear owned context
```

Key considerations:

- **Do not blindly trust client-supplied correlation ID headers.** Validate length, allowed characters, identifier format, and a policy to generate a new ID when input is invalid.
- **Do not put tokens, session cookies, or all headers into MDC**, because many appenders export every MDC field on every event, leaking sensitive data.
- **Async request boundaries:** when a servlet/request switches to async mode or callbacks run after the initial handling thread returns to the pool, understand the framework's exact lifecycle. Cleanup in a synchronous filter does not guarantee subsequent callbacks have the right context unless it is propagated.
- **Do not override the tracer's `traceId`.** If OpenTelemetry or a tracing framework manages trace/span context, read values from the active span and let instrumentation handle propagation/cleanup.
- **Context B must never contain A from the start.** A new request scope must set the new value accurately or represent it as missing per schema, never relying on a value "inherited" from a pooled thread.
- If a library/framework has already populated MDC, avoid calling `MDC.clear()` indiscriminately in lower layers, which would erase keys you do not own.

## 12. Schedulers, Message Consumers, and Batch Jobs

Stale context does not only happen in HTTP servers. For example, a `ScheduledExecutorService` runs the same worker for thousands of ticks; a message consumer receives many messages sequentially on one thread; a batch processor iterates over many items in the same job.

### Scheduled jobs

- Each execution needs a `runId` or `jobId` specific to that run.
- Set context at the start of `run()`, and clean up in `finally`.
- If a task is cancelled or times out, still ensure scope cleanup runs when control flow exits.
- Do not reuse the `requestId` of an HTTP request that triggered the job if the job later has an independent lifecycle; you may use a workflow `correlationId` if clearly defined.

### Message consumers

- Never treat message A's `messageId` as still valid when polling message B.
- During retries, attach `attempt` only for the current processing attempt, removing/restoring it before the next item.
- If requeuing/redirecting a message to another thread, propagate the right context or initialize a fresh context from validated message metadata.

### Batch loops

```java
// Illustrative snippet: LOG and jobs are already declared.
for (Job job : jobs) {
    String prior = org.slf4j.MDC.get("jobId");
    try {
        org.slf4j.MDC.put("jobId", job.id());
        LOG.info("event=job.started");
        process(job);
    } finally {
        if (prior == null) {
            org.slf4j.MDC.remove("jobId");
        } else {
            org.slf4j.MDC.put("jobId", prior);
        }
    }
}
```

This code is not standalone; it only illustrates **each item having its own scope**. If `job.id()` can be null, handle it according to the MDC API contract and schema before calling `put`. A failure in one item must not leave the wrong `jobId` active for the next item.

## 13. CompletableFuture, Reactive, and Context Propagation

With `CompletableFuture.supplyAsync(...)` or `thenApplyAsync(...)`, callbacks may run on an executor or the common pool that does not carry the caller's MDC. Even a callback without the `Async` suffix can sometimes run on the thread that completed the previous stage—so never **infer correct context from method names alone**.

Appropriate approaches depending on the system:

1. **Task decorators/wrappers** that capture context at task creation and set/restore it when the task runs.
2. **Framework-provided `TaskDecorator`/`ContextPropagator`** (if available), attached centrally to the executor.
3. **Tracing instrumentation** that propagates trace/span context per the observability stack's contract.
4. **Reactive Context** provided by the reactive framework, rather than relying on a `ThreadLocal` across threads.
5. **Per-event explicit attributes** for data belonging to a single log line, reducing reliance on thread context.

Do not build a one-size-fits-all propagation layer simply by copying `MDC.getCopyOfContextMap()` if the system has separate tracing or security contexts. Consider trace, identity, locale, and transaction contexts as well; at the same time, avoid carrying unnecessary sensitive data into background tasks.

**Specifically:** async logging (`AsyncAppender`/`AsyncLogger`) is different from async business execution. An appender can snapshot a `LogEvent`'s MDC at the moment a log is emitted, but **it does not automatically propagate context to a `CompletableFuture` task before that task calls the logger**.

## 14. Context Snapshots Must Be Safe and Meaningful

A good snapshot should:

- Be created **at the source** while the scope is valid, not "borrowed" from leftover data on a worker.
- Contain **allowlisted keys** and validated values; never hold request bodies, tokens, or heavy objects.
- Be passed as a **copy**, never sharing a mutable map modified by another thread.
- Have a **bounded lifetime**: task timeouts/cancellations should not leave context sitting in a queue indefinitely.
- Be **temporarily installed**, processed, and then restored/cleared in `finally`.
- Have a plan for **missing context**: null/absent per schema, never falling back to a stale value.
- Respect the **active trace/span**; never fake a `traceId` using `requestId`.

In pipelines with structured JSON logging, propagating context properly is not enough. The encoder/collector must output the exact field name and type. If `requestId` is in MDC but the encoder only writes `message`, querying by `requestId` still will not work. That is a **schema/encoding** bug, not stale context.

## 15. Testing Resistance to Stale Context

### 15.1. Force reuse of the same worker thread

Do not just send two requests in parallel and assume it "looks right"; they might run on two different threads so the bug stays hidden. Use a **single-thread executor** or an equivalent test setup:

```text
Worker #1:
  Request A: requestId=req-A
  Request A ends
  Request B: requestId=req-B
  Request B ends
  Task without request: requestId absent

PASS:
  Log A carries req-A.
  Log B carries req-B.
  Final log carries neither req-A nor req-B.
```

The demo in Section 9 deliberately uses a single-thread executor and `Future.get()` to test this exact scenario.

### 15.2. Testing exceptions and early returns

Make `processRequest()` throw a controlled exception. On the next task on the same worker, assert that `MDC.get("requestId")` no longer holds the old value. If a wrapper restores the caller's valid snapshot, compare against the pre-scope state rather than assuming it must always be empty.

### 15.3. Testing nested scopes

Set `operationId=checkout`, enter a temporary scope with `operationId=payment`, then verify it returns to `checkout`. Test both the normal path and the exception path. Asserting only "the `payment` field is gone" is not enough if you accidentally deleted `checkout`.

### 15.4. Testing propagation and cancellation

Test an executor task submitted while the caller has context, executed after the caller has already cleaned up, and verify it uses the right snapshot. Also verify that cancellation, timeout, and task faults leave no context behind on the worker. If a task never runs because it was cancelled, the closure holding the snapshot may remain in a queue/tracker for a while; design the lifecycle to avoid retaining unnecessary sensitive data.

### 15.5. Testing actual JSON output

For structured logging, parse the output after the encoder and assert:

```text
event=request.started, requestId=req-A
event=work.completed, requestId=req-A
event=request.started, requestId=req-B
event=work.completed, requestId=req-B
event=worker.idle, requestId absent or null per schema
```

Do not just assert that the string `"req-B"` appears. Verify the **exact key**, value, event, data type, and producer. With the demo's Logback text pattern, `none` is a display placeholder for a missing key—it does not mean JSON output should contain the literal `"none"`.

## 16. Common Mistakes and How to Fix Them

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Request B log carries `req-A` | Worker thread still has MDC from A. | Clear/restore context at request boundaries; test single-thread reuse. |
| Context remains after an exception | Cleanup placed after a call that can throw. | Use `try/finally` or a scoped API. |
| Subtask logger is missing `requestId` | MDC was only set on the caller thread. | Capture at submit time; set/restore in the worker. |
| "Fixed" by setting MDC inside callback after it starts | Source context was already cleaned up or worker has old value. | Pass snapshot/correlation ID from task creation time. |
| Nested operation loses outer context | Calling `remove(key)` instead of restoring prior value. | Save the old value and restore it in `finally`. |
| Calling `MDC.clear()` in a service method wipes trace | Service does not own the entire MDC. | Only remove keys you manage; use ownership-aware scopes. |
| `putCloseable` loses the old value on close | Close only cleans up the key, does not restore snapshot as expected. | Use a helper that restores the key or map. |
| Assuming `InheritableThreadLocal` propagates across a pool | Pool workers were created before the request. | Use explicit propagation or framework task decorators. |
| Async task's context changes as caller continues | Shared mutable map or captured at the wrong time. | Take an immutable snapshot at submit time; avoid sharing maps. |
| `traceId` does not link to tracing | Custom-generated ID or stale trace context. | Read from active tracer; use official propagation. |
| IDs bleed across tenants | `tenantId` not cleaned up; too many request fields in MDC. | Dedicated scope, allowlist, and cross-tenant tests. |
| `AsyncAppender` doesn't "fix" stale context | Confusing async output with async execution. | Handle context before the task calls the logger. |
| Context is in MDC but JSON lacks the field | Encoder doesn't export MDC or schema mapping is wrong. | Configure structured encoder and inspect actual JSON. |
| Event has right context but wrong `outcome` | `outcome` placed in request scope and not updated after retry. | Emit `outcome` on the event with the final result. |
| Alerts show sensitive data in logs | Tokens, cookies, or headers put into MDC. | Exclude/strip sensitive fields at source, retention, and access control. |
| Duplicate logs from appenders/root | Additivity/handler misconfiguration, not stale MDC. | Check appender configuration and propagation separately. |

## 17. Pre-Deployment Checklist

- [ ] Is the **owner** of each context key defined: request, trace, job, operation, or resource?
- [ ] At the start of a request/job, is context initialized from trusted data rather than "inheriting" leftover IDs?
- [ ] Does every code path have a `finally` or scope close, including exceptions and early returns?
- [ ] Do nested scopes **restore** old fields instead of only removing them?
- [ ] Is `MDC.clear()` avoided in layers that do not own the entire context?
- [ ] Are pooled worker threads tested for consecutive reuse from request A to request B?
- [ ] Are async task submit snapshots taken at the right time without sharing mutable maps?
- [ ] Is Executor/CompletableFuture/reactive/tracing propagation integrated and verified?
- [ ] When `requestId`/`traceId` is missing, is absent/null handled per schema instead of reusing old values?
- [ ] Are tokens, session cookies, passwords, headers, and unnecessary payloads excluded from MDC?
- [ ] Are context IDs validated for length and allowed characters when coming from external inputs?
- [ ] Do all producers agree on `requestId`, `traceId`, `tenantId`, and their data types?
- [ ] Does the structured encoder actually export context as fields if dashboards need to query by field?
- [ ] Are there tests for exceptions, nested scopes, cancellation, contextless tasks, and cross-tenant isolation?
- [ ] Is there a way to detect a worker still holding context before accepting a new task when it should be clean?

## 18. Self-Check Questions

1. Why do pooled threads cause stale MDC even when the code only uses a single `ThreadLocal`?
2. Why is cleanup after `processRequest()` outside of `finally` insufficient?
3. With nested scopes, is `remove("operationId")` always correct?
4. Why does `MDC.clear()` on the main thread not clear MDC in an executor worker?
5. What is the risk of capturing a snapshot inside the worker after the caller has already cleaned up?
6. Does `AsyncAppender` automatically propagate `requestId` to `CompletableFuture`?
7. Why does `InheritableThreadLocal` fail to guarantee correct context when using a thread pool?
8. In the Java 17 demo, why is `event=worker.idle` expected to have `requestId=none`?
9. When should you use `MDC.clear()` versus restoring an old key?
10. If a request has no active trace, should you keep the `traceId` from the previous request to make tracing easier?
11. Why can a wrong `tenantId` field become a security risk rather than just a dashboard bug?
12. Is a test that only observes `req-B` present enough to prove B's context was not polluted?

**Conclusion:** To **avoid stale context**, manage MDC/ThreadContext as **scoped, owned state** rather than permanent per-thread metadata storage. **Setting it at the right time, snapshotting before switching threads, cleaning up/restoring in `finally`, isolating context per request/operation, and testing thread reuse** are the most important practices. These rules keep correlation accurate, reduce the risk of misattributing logs to another request or tenant, and protect incident investigation integrity.