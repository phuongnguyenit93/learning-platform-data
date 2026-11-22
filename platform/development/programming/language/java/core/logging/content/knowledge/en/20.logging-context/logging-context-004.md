# Tenant Context in Java Logging: Tag the Right Tenant, Never Leak Context

## 1. What Is Tenant Context?

In a **multi-tenant** application, a single software system serves multiple organizations, customers, or data spaces known as **tenants**. The same Java service and the same logger can handle requests for `tenant-A`, `tenant-B`, and hundreds of other tenants.

**Tenant context** is the context indicating **which tenant the current unit of processing belongs to**, typically containing a stable identifier such as `tenant_id`. When included in logging, it helps engineers distinguish events from multiple tenants passing through the same application.

For example, if you only have:

```text
INFO  event=order_created order_id=ORD-101
WARN  event=payment_retry order_id=ORD-102
```

operators cannot tell which tenant each order belongs to. With tenant context:

```text
INFO tenant_id=tenant-A event=order_created order_id=ORD-101
WARN tenant_id=tenant-B event=payment_retry order_id=ORD-102
```

investigations can be scoped down to a specific tenant.

**Two core notes:**

1. **Tenant context is for observability and may assist in passing business context**, but it is **not a mechanism for authentication, authorization, or data isolation**. Never grant database access just because `MDC.get("tenant_id")` returns a string.
2. **Context must be accurate throughout its entire lifecycle and at the exact moment a log is recorded.** If the tenant from a previous request remains on a reused thread, the system may mislabel the next request's tenant, creating security risks and misleading investigations.

Within **Logging context**, the tenant ID should be treated as a **dynamic per-event data field**, much like a correlation ID or request ID, rather than a logger name, global constant, or service name.

## 2. Distinguishing Different Types of Context

| Data | What does it indicate? | Typical scope |
| --- | --- | --- |
| `tenant_id` | Tenant associated with the operation | Request, message, job, or unit of work |
| `request_id` | A single incoming request to a service | One request |
| `correlation_id` | A chain of related operations | May span multiple services |
| `trace_id` / `span_id` | Correlation data for distributed tracing | Trace and span |
| `user_id` / `actor_id` | Subject performing the action | User or service account |
| `service.name` | Logical service name | Usually stable within an instance |
| `environment` | Runtime environment such as staging/production | Deployment |
| `order_id` | Business entity being processed | A business event or processing flow |
| `tenant_scope` | Whether a task belongs to one tenant or multiple | Specific job or event |

**Tenant ID is not user ID.** One user can belong to multiple tenants; one tenant can have multiple users. When a user switches workspaces, the tenant context of subsequent requests may change even though `user_id` stays the same.

**Tenant ID is not trace ID.** Many traces belong to the same tenant; a gateway trace or administrative task can also involve multiple tenants. Never use a trace ID or request ID as a substitute for the tenant.

**Tenant ID is not service name.** A single `billing-service` instance can handle multiple tenants concurrently, so do not attach the current request's tenant to the **resource-level `service.name`** or a process-wide environment variable.

An event can be represented in structured form:

```json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "INFO",
  "service": "order-service",
  "tenant_id": "tenant-A",
  "event": "order_created",
  "order_id": "ORD-101",
  "correlation_id": "req-7c"
}
```

This is an **illustrative schema**, not the default output of any Java logging backend. Producing output like this requires the corresponding encoder/layout and collector pipeline.

## 3. Tenant Context Must Come from a Trusted Source

A lesson on tenant logging cannot simply say "read `X-Tenant-ID` from the HTTP header and log it." In a multi-tenant application, **choosing the wrong tenant from an untrusted source both produces false logs and may signal a severe authorization bug**.

A reference flow:

```text
HTTP request / message / job
             |
             v
    Authentication boundary
   (token/session mTLS/identity)
             |
             v
    Tenant resolution + authorization
  - Which tenant is requested?
  - Is the principal authorized for that tenant?
  - Does the resource belong to that tenant?
             |
             v
       Verified tenant ID
             |
             v
    Scoped tenant context
             |
             v
    Business code + logging
             |
             v
        Cleanup / restore
```

**Do not blindly trust:**

- Client-supplied headers such as `X-Tenant-ID: tenant-admin`.
- Query parameters `?tenant=...` or path segments `/tenants/{tenantId}` before authorization is checked.
- Cookies whose origin has not been verified.
- `tenant_id` values in Baggage, MDC, trace metadata, or logging headers from an untrusted service.
- Data inside a LogEvent or a logger name as proof that the request is actually authorized.

A sound architectural principle:

1. Authenticate the principal using the application's mechanism.
2. Resolve the requested tenant using valid identity and resource information.
3. **Authorize tenant access** and verify the tenant–resource relationship at the appropriate business/DB layer.
4. Normalize the tenant identifier into a stable ID with constrained characters and length.
5. Put the **verified** ID into the logging context for the scope of the work.
6. Clear or restore the context when finished.

Calls like `TenantContext.open(verifiedTenantId)` in this article happen **after the tenant has been verified**. They do not perform authorization checks themselves.

## 4. Scope: Why Must You Clean Up After Setting?

In Java, many logging context mechanisms store data bound to a **thread**. If an HTTP server uses a thread pool, a single thread may sequentially process a request for tenant A and then a request for tenant B.

If you only set it:

```java
// Bug illustration: no cleanup.
MDC.put("tenant_id", verifiedTenantId);
processRequest();
```

and forget `MDC.remove` or snapshot restoration, the next request can inherit stale metadata on the same thread—especially if the next request hits an error branch before setting a new tenant.

A safe scope needs to:

- **Set** the context after the tenant is verified.
- **Keep** the context across functions in the same flow that need to log.
- **Restore the previous value or remove the key** after the scope exits, even when an exception is thrown.
- **Never extend the scope** into another tenant's work.
- **Propagate context explicitly** across thread or async boundaries.
- **Take a snapshot at the right time** if events need to be logged asynchronously.
- **Never reuse mutable context objects** across independent requests.

A `try/finally` or `try-with-resources` pattern keeps the lifecycle explicit:

```java
String previous = MDC.get("tenant_id");
MDC.put("tenant_id", verifiedTenantId);
try {
    processRequest();
} finally {
    if (previous == null) {
        MDC.remove("tenant_id");
    } else {
        MDC.put("tenant_id", previous);
    }
}
```

This is an **illustrative snippet inside a service that already has SLF4J and the corresponding variables/methods**, not a standalone program. It **restores** the previous context when scopes are nested; simply calling `remove` could accidentally erase the outer scope's value.

**Note:** if the request boundary owns the entire MDC, it may decide to call `MDC.clear()` at the end of the request. However, a sub-library should not call `MDC.clear()` indiscriminately because doing so can wipe out `trace_id`, `request_id`, and other fields set by the framework.

## 5. Standalone Java 17+ Example: Two Tenants Sharing a Thread Pool

This example demonstrates the **scoped tenant context** principle using pure JDK classes. The program:

1. Defines a `TenantContext` backed by `ThreadLocal<String>`.
2. Processes two tenants sequentially on the main thread.
3. Submits a task to the **same worker thread** of an `ExecutorService`.
4. **Captures the tenant ID on the submitting thread and re-applies it on the worker thread**.
5. Logs a JUL `LogRecord` with `tenant_id` captured at **LogRecord creation time**.
6. Automatically restores context using `AutoCloseable`.
7. Produces deterministic stdout to make tenant-leak checks easy.

**Limitations:** the example uses two hardcoded tenant IDs assumed to be valid for the exercise. It **does not perform authentication/authorization**, is not a production tenant-isolation solution, and does not replace MDC/`ThreadContext` configuration when using a real logging backend.

Save the full code as **`TenantLoggingDemo.java`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class TenantLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(TenantLoggingDemo.class.getName());

    private TenantLoggingDemo() {
    }

    private static final class TenantContext {
        private static final ThreadLocal<String> CURRENT =
                new ThreadLocal<>();

        private TenantContext() {
        }

        static Scope open(String verifiedTenantId) {
            if (verifiedTenantId == null
                    || !verifiedTenantId.matches("[A-Za-z0-9_-]{1,32}")) {
                throw new IllegalArgumentException(
                        "Invalid tenant identifier");
            }

            String previous = CURRENT.get();
            CURRENT.set(verifiedTenantId);
            return new Scope(previous);
        }

        static String current() {
            return CURRENT.get();
        }

        static String required() {
            String tenant = CURRENT.get();
            if (tenant == null) {
                throw new IllegalStateException(
                        "Tenant context missing");
            }
            return tenant;
        }

        static final class Scope implements AutoCloseable {
            private final String previous;
            private final Thread owner;
            private boolean closed;

            private Scope(String previous) {
                this.previous = previous;
                this.owner = Thread.currentThread();
            }

            @Override
            public void close() {
                if (Thread.currentThread() != owner) {
                    throw new IllegalStateException(
                            "Close scope on owning thread only");
                }
                if (closed) {
                    return;
                }
                if (previous == null) {
                    CURRENT.remove();
                } else {
                    CURRENT.set(previous);
                }
                closed = true;
            }
        }
    }

    private static void event(String name, String orderId) {
        // Snapshot the tenant immediately when creating the LogRecord.
        LOG.log(Level.INFO,
                "event={0} tenant_id={1} order_id={2}",
                new Object[] {
                        name, TenantContext.required(), orderId
                });
    }

    private static void process(
            ExecutorService pool, String verifiedTenantId,
            String orderId) throws Exception {
        try (TenantContext.Scope request =
                     TenantContext.open(verifiedTenantId)) {
            event("order_received", orderId);

            // ThreadLocal does not propagate automatically across ExecutorService.
            String snapshot = TenantContext.required();

            Future<?> result = pool.submit(() -> {
                try (TenantContext.Scope task =
                             TenantContext.open(snapshot)) {
                    event("order_processed", orderId);
                }
            });
            result.get();
        }
    }

    public static void main(String[] args) throws Exception {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Formatter formatter = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        };

        StreamHandler stdout =
                new StreamHandler(System.out, formatter);
        stdout.setEncoding("UTF-8");
        stdout.setLevel(Level.INFO);
        LOG.addHandler(stdout);

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            process(pool, "tenant-A", "ORD-101");
            process(pool, "tenant-B", "ORD-102");

            stdout.flush();
            System.out.println(
                    "main_context_cleared="
                    + (TenantContext.current() == null));
        } finally {
            pool.shutdown();
            LOG.removeHandler(stdout);
            stdout.flush();
            // Do not close StreamHandler because it will close System.out.
        }
    }
}
```

From the directory containing the file, compile and run with JDK 17+:

```bash
javac -encoding UTF-8 TenantLoggingDemo.java
java TenantLoggingDemo
```

**Exact stdout when the program runs normally:**

```text
INFO event=order_received tenant_id=tenant-A order_id=ORD-101
INFO event=order_processed tenant_id=tenant-A order_id=ORD-101
INFO event=order_received tenant_id=tenant-B order_id=ORD-102
INFO event=order_processed tenant_id=tenant-B order_id=ORD-102
main_context_cleared=true
```

**Application stderr:** no records during normal operation. JVM/environment diagnostics or I/O errors are not part of the expected output.

### Decision Breakdown

- `ThreadLocal<String>` stores the tenant per current thread, not as a global variable shared across all requests.
- `TenantContext.open` validates the format of the tenant ID; **this is not authorization**. In a real application, the input must come from a trusted resolution/authorization step.
- `Scope` remembers the previous value and restores it on close. With properly nested LIFO scopes, the outer scope's tenant is not accidentally erased.
- `Scope` records `owner` to prevent closing from another thread. Each scope is closed on the exact thread that opened it.
- `TenantContext.required()` ensures an event requiring a tenant cannot silently log with a `null` context.
- `event(...)` places the tenant ID into the **immutable arguments of the `LogRecord`** at the call site. It does not rely on a `Formatter` running later still being able to read the original `ThreadLocal`.
- `Executors.newSingleThreadExecutor()` has a single worker **reused** for both tenant A and tenant B. The worker does not rely on automatic `ThreadLocal` inheritance; the task sets up its own scope from the snapshot.
- `Future.get()` waits for the task to complete, so the order of the five stdout lines is deterministic.
- `StreamHandler(System.out, formatter)` writes to stdout when flushed; JUL's default `ConsoleHandler` writes to stderr and is unsuitable if you want to demonstrate stdout output.
- `LOG.setUseParentHandlers(false)` prevents a `LogRecord` from also propagating to parent handlers and producing duplicate records.
- `stdout.flush()` before `println` preserves observation order; it does not imply logs are durably stored in a collector.
- `StreamHandler` is not closed in the demo because `StreamHandler.close()` would close the process-wide `System.out`.

### What the Demo Does Not Prove

This program does **not** guarantee database tenant isolation, does not simulate requests carrying real tokens, does not test an async logging backend or distributed tracing system, and does not prove durability of a log collector. It proves only one thing: **two tenants can share a single worker thread while each log event still receives the right tenant ID if context is propagated and cleaned up properly**.

## 6. Why You Should Not Read ThreadLocal in an Asynchronous Formatter

This is a subtle trap. Suppose code writes:

```java
// Dangerous idea when the formatter may run on another thread:
String tenant = TenantContext.current();
```

If that code runs inside a `Formatter`/`Encoder` executed **later** on an async logging thread, the `ThreadLocal` being read belongs to the **formatter thread**, not necessarily the thread that created the event. As a result, the tenant may be empty or wrong.

The principled approach:

1. **Capture the tenant when emitting the event** on the thread that holds the context.
2. **Attach the tenant to the `LogEvent`/`LogRecord`** or structured key-value/metadata supported by the backend.
3. Let the async appender/encoder serialize the **captured data**, rather than reading an arbitrary request-scoped `ThreadLocal` when the consumer runs.
4. Test with your actual backend, because how context data is snapshotted and when events are prepared depends on the logging implementation.

In this article's `event(...)` example, the `LogRecord` is created with **a parameter containing the tenant ID**, so the `Formatter` never needs to access `TenantContext.current()` to retrieve the tenant.

**Do not assume "every logging framework snapshots MDC identically in every mode."** Different backends optimize async queues, mementos, reusable events, or custom encoders differently. Verify tenant data in real logs and test behavior under queue pressure/backpressure.

## 7. SLF4J MDC: `tenant_id` in the Logging API

In many Java applications using SLF4J + Logback or an MDC-capable provider, **Mapped Diagnostic Context (MDC)** is the standard way to include the tenant ID across log lines in the same scope.

```java
import org.slf4j.MDC;

// verifiedTenantId has been verified at the authentication/authorization layer.
try (MDC.MDCCloseable ignored =
             MDC.putCloseable("tenant_id", verifiedTenantId)) {
    LOG.info("event=order_received order_id={}", orderId);
    LOG.info("event=order_completed order_id={}", orderId);
}
```

This is a **snippet inside a class with an SLF4J `LOG`**, not a standalone program. `putCloseable` creates a scope and on close **removes the `tenant_id` key** from MDC. **It does not automatically restore the previous value of the same key** if the scope is nested inside an earlier scope.

For nested scopes, use the save-and-restore pattern:

```java
String previous = MDC.get("tenant_id");
MDC.put("tenant_id", verifiedTenantId);
try {
    processTenantWork();
} finally {
    if (previous == null) {
        MDC.remove("tenant_id");
    } else {
        MDC.put("tenant_id", previous);
    }
}
```

If this method belongs to a sub-library, it should not call `MDC.clear()`, as that could erase `trace_id`, `request_id`, or metadata set by a request filter.

### MDC Does Not Guarantee the Backend Always Displays the Tenant

When using **Logback `PatternLayout`**, you can configure:

```xml
<pattern>%d{ISO8601} %-5level tenant_id=%X{tenant_id} %logger - %msg%n</pattern>
```

This is a **pattern snippet inside a Logback encoder**, not a complete `logback.xml`. You need a Logback provider, a Console/File Appender, and a matching pattern encoder.

If the backend uses a JSON encoder, verify that **MDC is emitted as a `tenant_id` JSON field**. Some encoders nest MDC inside another object, some require an explicit allowlist, and very basic providers do not output MDC at all. A successful `MDC.put` call **does not prove the log collector will have a tenant field**.

### MDC Is a Logging Aid, Not a `TenantResolver`

`MDC.get("tenant_id")` only retrieves a value previously placed in the context. **Do not use it as the source of truth for authorization, tenant-aware SQL filtering, or billing.** Business code should receive a verified tenant/principal object and use it through explicit authorization APIs. Syncing that tenant ID into MDC is solely for observability.

## 8. Propagating MDC Across `ExecutorService`

SLF4J MDC is usually bound to the current thread's context depending on the adapter/backend. When submitting tasks to a pool, **never assume MDC propagates automatically**. You can capture a snapshot of MDC from the source thread:

```java
Map<String, String> captured = MDC.getCopyOfContextMap();

executor.submit(() -> {
    Map<String, String> oldWorker =
            MDC.getCopyOfContextMap();
    try {
        if (captured == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(captured);
        }
        performWork();
    } finally {
        if (oldWorker == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(oldWorker);
        }
    }
});
```

This is an **illustrative pattern** in a class that imports `java.util.Map` and `org.slf4j.MDC` and has `executor`/`performWork`. Key points to understand:

- `getCopyOfContextMap()` returns a **copy**; it can return `null`.
- The snapshot reflects data at **submission time**, not a live reference to a map updated later.
- The worker thread may hold preexisting metadata; the example **saves and restores** that map rather than leaving data from a previous task behind.
- `MDC.setContextMap(...)` replaces the calling thread's entire context map, not just a single key. This pattern requires clear **context ownership** when applied in a framework.
- If the task spawns further child tasks on new threads, propagation must be handled at **every async boundary**.
- The snapshot may contain information that should not be passed to other tasks; control which fields are allowed to propagate and respect trust boundaries.

In a real project, if your framework provides an appropriate **task decorator, context propagation library, or instrumentation**, prefer the tested mechanism instead of copying snippets everywhere. Still, you must understand the snapshot–restore model to avoid context leaks.

## 9. Log4j2 `ThreadContext`: Scoped Tenant Map

In Log4j2, `org.apache.logging.log4j.ThreadContext` provides both a **Thread Context Map** (like MDC) and a **Thread Context Stack** (NDC). To attach a tenant ID:

```java
import org.apache.logging.log4j.ThreadContext;

String old = ThreadContext.get("tenant_id");
ThreadContext.put("tenant_id", verifiedTenantId);
try {
    LOG.info("event=order_created order_id={}", orderId);
} finally {
    if (old == null) {
        ThreadContext.remove("tenant_id");
    } else {
        ThreadContext.put("tenant_id", old);
    }
}
```

This is a **snippet inside a class using the Log4j2 API**. In `PatternLayout`, you can print the tenant:

```xml
<PatternLayout charset="UTF-8"
    pattern="%d{ISO8601} %-5p tenant_id=%X{tenant_id} %c{1} - %m%n"/>
```

This is an **XML Layout placed inside an Appender**, not a complete `log4j2.xml` file.

### `CloseableThreadContext`

Log4j2 provides the `CloseableThreadContext` API:

```java
try (CloseableThreadContext.Instance ignored =
             CloseableThreadContext.put(
                     "tenant_id", verifiedTenantId)) {
    LOG.info("event=order_created order_id={}", orderId);
}
```

You need to import `org.apache.logging.log4j.CloseableThreadContext`. This approach provides **automatically managed scope** for the Thread Context. When nesting scopes or combining with framework code, test the exact restoration behavior for your version/backend and avoid external code modifying the same key without conventions.

### Thread Pools with Log4j2

The Log4j2 documentation describes capturing `ThreadContext.getImmutableContext()` and then using `CloseableThreadContext.putAll(...)` in the worker. The idea:

```java
Map<String, String> snapshot =
        ThreadContext.getImmutableContext();

executor.submit(() -> {
    try (CloseableThreadContext.Instance ignored =
                 CloseableThreadContext.putAll(snapshot)) {
        LOG.info("event=async_work_started");
        performWork();
    }
});
```

This is a **snippet** requiring `java.util.Map` and the Log4j2 classes. Neither `ThreadContext` nor `MDC` means an arbitrary async system will automatically transfer data. Support varies across backends and bridges; always verify the actual output.

Apache documentation: https://logging.apache.org/log4j/2.x/manual/thread-context.html

## 10. Thread Pools, Virtual Threads, Reactive, and `CompletableFuture`

### Thread Pools and Task Reuse

A request can execute on a worker thread that previously handled a different tenant. Therefore you must **clear/restore in `finally`**, not only set the tenant when a thread is created. Minimum test: task A with tenant A, task B on the **same worker** with tenant B, task C with no tenant that must not be labeled A or B.

### `CompletableFuture`

`CompletableFuture.supplyAsync(...)` and `thenApplyAsync(...)` may run on different executors/threads. Calling `MDC.put` before `supplyAsync` does not guarantee callbacks will have that context.

Design approach:

- Capture the **verified tenant ID** or context snapshot at task creation time.
- In **every async callback that needs the tenant**, open a scope inside the callback and close it in `finally`.
- Never open a `ThreadLocal` scope on the submitting thread and close it on the worker thread; a scope must be created and closed on the **same thread**.
- For callbacks that run inline (`thenApply`) or switch threads depending on completion timing, still define clearly who owns the context.
- When fanning out multiple tasks, pass an immutable snapshot rather than sharing a mutable map.

### Virtual Threads in JDK 21+

Virtual threads make it cheap to spawn many lightweight tasks, but they **do not replace the concept of context scope**. `ThreadLocal` remains bound to the current thread; moving a request onto another virtual thread does not automatically transfer the source thread's context as expected. Design explicit context propagation or use framework abstractions; do not rely on `InheritableThreadLocal` defaults to solve every case.

The main runnable example in this article targets **Java 17** and does not require virtual threads.

### Reactive Programming

With Reactor, RxJava, or other reactive streams, callbacks can execute across multiple threads. **`ThreadLocal` is not always the right place to store context across an entire pipeline.** In Project Reactor, a common design uses **Reactor Context** with appropriate context-propagation bridges, rather than setting MDC once on the request-receiving thread and hoping it follows every signal.

**General rule:** context must follow the **unit of work**, not assume it stays on one OS/JVM thread for the entire request.

## 11. Tenants in Scheduled Jobs, Message Consumers, and Batches

HTTP requests are not the only source of logs. A SaaS system may run:

- A scheduler processing tenant A's data every hour.
- A message consumer receiving `order_created` from a queue.
- A retry worker reprocessing an old order.
- A nightly batch iterating sequentially through many tenants.
- A system-wide admin task that does not belong to any single tenant.

### Message Consumers

Suppose a message carries `tenant_id`. **Reading the field does not mean the tenant is trusted.** The consumer should:

1. Verify the origin/identity and permissions of the sender according to system design.
2. Resolve the message's tenant and verify its relationship with the resource or event.
3. Open a tenant scope for the **duration of message processing**.
4. Include the tenant ID in operationally meaningful events.
5. Close the scope whether processing succeeds, retries, or routes to a dead-letter queue.
6. Propagate tenant/trace metadata according to policy when emitting new messages.

A message with the wrong tenant may indicate a security flaw, a routing bug, or corrupted data—not merely a "missing log field."

### Multi-Tenant Batches

If a job iterates over tenant A and then tenant B:

```text
job started (system-wide scope)
  |
  +-- tenant A scope -> tenant A events -> close
  |
  +-- tenant B scope -> tenant B events -> close
  |
job completed (system-wide scope)
```

Do not attach an arbitrary `tenant_id` to the entire batch. System-wide events can use `scope_type=SYSTEM` or `tenant_scope=MULTI` **if defined by your schema**; per-tenant work should have an accurate tenant scope.

An administrative task authorized to operate across multiple tenants **must not** use logging context as a way to bypass the authorization layer. The actor's permissions and target tenant must be verified against trusted business data.

### Retries, DLQs, and Replays

During a retry, tenant context must be bound to the **unit of work being retried**, not the most recent request or the tenant of an idle worker. At the same time, `message_id`, `attempt`, and `reason_code` should be logged so operators can distinguish multiple attempts for the same work. One transaction may produce multiple log lines; never count success log lines as the official transaction count.

## 12. Tenant ID in JSON Structured Logging

An event can be described in JSON as:

```json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "WARN",
  "service": "billing-service",
  "tenant_id": "tenant-B",
  "event": "invoice_retry_scheduled",
  "invoice_id": "INV-7",
  "attempt": 2,
  "reason_code": "UPSTREAM_TIMEOUT",
  "trace_id": "b3c9a1"
}
```

This is an **illustrative application schema**. For the pipeline to query `tenant_id` as a field, the **backend/encoder/collector** must actually store that field, not merely print the text `tenant_id=...`.

Compare:

```text
WARN tenant_id=tenant-B event=invoice_retry_scheduled
```

with the JSON object above:

- Plain text is easy to read directly, but the collector may have to parse fields out.
- JSON preserves field names and types more cleanly with the right encoder, but **only if the parser actually decodes and indexes it**.
- Some systems write MDC into `contextMap` or a nested object rather than root `tenant_id`. Queries must target the actual field path.
- If `tenant_id` is omitted in the encoder, calling `MDC.put` will not make it magically appear.
- If a tenant ID contains special characters, the JSON encoder must escape them properly, and the application should constrain input to avoid untrusted data.

With Log4j2 you can use `JsonTemplateLayout` from the `log4j-layout-template-json` artifact and configure a template with the corresponding resolver/context fields; with Logback, choose an appropriate JSON encoder. Do not assume default templates across all backends share the same fields or paths.

### Consistent Field Types

`tenant_id` is usually a **string identifier**, even when the value looks numeric. Using `"tenant_id":"000123"` preserves leading zeros, whereas a number `123` does not.

Do not turn `tenant_id` into a JSON key name, such as `"tenant-A":true`, because that creates an **unbounded dynamic schema**. The tenant should be the **value of a stably named field**.

## 13. Tenant ID and Cardinality: Indexes, Labels, and Metrics

In a centralized logging system, there may be very many tenants. **High cardinality** describes a field with many distinct values. Including the tenant ID in structured logs is useful, but **that does not mean it should become an indexed label everywhere**.

### Example with Loki

Loki organizes log streams using sets of *labels*. If every `tenant_id`, `request_id`, or `order_id` becomes an indexed label, the number of label combinations can explode and severely degrade cost and performance.

A usually sensible approach:

- Use labels with relatively few values: `service`, `environment`, `cluster`, or `namespace`.
- Put `tenant_id` in the log body or **structured metadata** if your architecture and version support it, and query using the appropriate mechanism.
- Only promote tenant to a label if you have measured cardinality, have a clear requirement, and operations approves it.

**Do not equate "`tenant_id` must be queryable" with "`tenant_id` must be an indexed label."** Backends differ in indexing, partitioning, and structured metadata strategies.

### Metrics and Tracing

A metric such as `http_requests_total{tenant_id="..."}` can cause a time-series explosion when the tenant count is large. Do not carry logging rules over to metrics while ignoring cardinality.

For tracing, the tenant ID can be a span attribute when permitted by data policy, but it will not automatically appear on every span just because MDC contains `tenant_id`. Instrumentation or a processor must explicitly add the attribute while considering privacy.

## 14. OpenTelemetry: Baggage Is Not Tenant Authorization

OpenTelemetry defines several concepts:

- **Span context** such as trace/span IDs for correlation.
- **Baggage**: key-value pairs that can be propagated across process/service boundaries.
- **Span/log attributes**: metadata attached to telemetry data.
- **Resource**: metadata of the entity emitting telemetry, such as `service.name`.

An application may want to pass tenant context between services via headers or Baggage. This requires great care:

1. Baggage can be **automatically propagated** across network calls made by instrumentation.
2. Baggage can arrive from **untrusted sources** or be modified; there is **no built-in integrity check** guaranteeing it represents a verified tenant.
3. Do not put secrets or unnecessary PII into Baggage; data may be forwarded to third-party endpoints.
4. Data in Baggage **does not automatically become a log/span attribute** unless instrumentation adds it.
5. Trace context aids diagnostics; **it does not grant tenant access**.
6. When a service receives Baggage, it must cross-check it against the request/message's identity and authorization.
7. If multiple tenants share a service instance, a dynamic tenant should not be assigned to `service.name` or any process-wide resource attribute.
8. If propagation is needed, use a stable ID, limit its size, consider propagating only within trusted boundaries, and prevent leakage to external services.

**Security anti-pattern:** reading `baggage.tenant_id` from a public request and using it to filter SQL, or treating it as proof that the caller may read that tenant's orders.

**Sound conceptual pattern:** authenticated and authorized identity determines tenant A; code stores tenant A in a trusted business object, attaches tenant A to the logging context, and propagates only approved metadata over distributed tracing.

OpenTelemetry documentation on Baggage risks: https://opentelemetry.io/docs/concepts/signals/baggage/

## 15. Tenant Context and Data Security Boundaries

A `tenant_id` field in logs never replaces mechanisms such as:

- Authentication and token validation.
- Tenant-level and per-resource authorization.
- Properly designed and tested tenant-aware queries or row-level security.
- Architectural database/schema/storage isolation.
- Access control on the log viewer and log index.
- Controls over log export paths, secrets, and retention.

### Do Not Use MDC as a Security Principal

Anti-pattern example:

```java
// Broken security model: MDC is metadata, not proof of authorization.
String tenantId = MDC.get("tenant_id");
repository.findAllByTenantId(tenantId);
```

This is **dangerous illustrative code**, not a solution to deploy. Any code able to set MDC in the same execution flow can alter the value; moreover, a leaked context from a previous request can cause the query to run against the wrong tenant.

The business layer should use a **VerifiedTenant/AuthenticatedPrincipal** object from a trusted boundary with explicit authorization policies. Only afterward should a safe field (such as an opaque ID) be synced to the log context.

### Log Viewers Must Enforce Their Own Authorization

A shared log search system may hold events from thousands of tenants. **A UI filter** like `tenant_id=tenant-A` does not by itself prevent users from viewing tenant B's logs. If tenants have self-service log viewing, the **log store and query API** must enforce user/tenant authorization—not just CSS or a dropdown.

Tenant IDs stored in logs can also be sensitive under organizational policy. Consider pseudonymization, limiting linkability to specific individuals or companies, and retention periods.

## 16. Choosing a Suitable Tenant Identifier for Logging

A good tenant identifier for logging is typically:

1. **Stable** over the timeframe needed for investigations.
2. **Free of sensitive information** such as email addresses, phone numbers, or full customer names.
3. **Standardized in format and bounded in length**, such as an opaque ID or controlled internal slug.
4. **Resistant to log injection**, containing no newline or control characters.
5. **Not easily confused with a user ID** or service ID.
6. **Consistent across services** in the same pipeline.
7. **Governed by rules for deleted/merged/split tenants** so historical logs remain interpretable.
8. **Never reused for another tenant** if used for auditing or historical queries.
9. **Backed by a mapping policy** when upstream and downstream systems use different tenant namespaces.

Not every tenant ID needs to be a UUID, though if you use numeric IDs in JSON, consider emitting them as **strings** to preserve the exact identifier and avoid parser type coercion.

**Especially avoid** putting full organization names or user data into a publicly visible tag. An opaque tenant ID reduces exposure, though it does not automatically make data non-sensitive; the log store may still link the ID to a specific account.

## 17. Tenant Context and Log Levels

`tenant_id` is a **context field**, not a log level like `INFO`, `WARN`, or `ERROR`. The log level must reflect the technical/business situation, not "this tenant is a VIP customer" unless governed by a controlled operational policy.

Examples:

| Situation | Reference log level | Should tenant field be present? |
| --- | --- | --- |
| Order created successfully | `INFO` | Yes, if event belongs to tenant and policy allows |
| Rejected by valid business rule | `INFO` | Yes, to distinguish the source |
| Cache unavailable, fallback succeeded | `WARN` or `DEBUG` depending on ops | Yes, if it affects a tenant |
| Unexpected payment failure | `ERROR` at handling boundary | Yes, without logging card/token data |
| App startup before any request | `INFO` | No, this is a system-wide event |
| Background task processing multiple tenants | Depends on event | Per-tenant logs carry ID; summary uses `scope_type=SYSTEM` or `MULTI` per schema |
| Authentication failed before tenant verification | `INFO`/`WARN` per policy | Do not assign tenant from untrusted headers |

**Do not force a tenant ID onto every `LogEvent`.** Application startup logs, global configuration, or pre-authentication system errors may have no specific tenant. What matters is distinguishing **"no tenant because not applicable"** from **"missing tenant due to a bug in a verified request."**

A good schema might specify:

- For `event=order_created`, `tenant_id` is **required**.
- For `event=service_started`, `tenant_id` is **not applicable**.
- For `event=auth_rejected`, do not take the tenant ID from unverified client data; if `requested_tenant_id` is needed, mark it as **untrusted** and govern it with a separate policy.

## 18. Propagation Across Services and Messages

For a request flowing from an API gateway through `order-service` to `billing-service`:

```text
Caller
  |
  v
Gateway (authenticate + authorize)
  |
  v
Order service ----> Billing service
  |                        |
  v                        v
Log tenant_id=tenant-A   Log tenant_id=tenant-A
  |                        |
  +------------+-----------+
               |
               v
       Central log collector
```

To achieve the same trusted tenant ID:

1. The gateway must verify the identity and permissions for the requested tenant.
2. Downstream services must have a **trust model**: verify the calling service, token/delegation, or re-authentication policy—never treat public Internet headers as truth.
3. The communication layer passes tenant identity/context through an approved mechanism; do not simply add a public header and trust everything.
4. Each service resolves/verifies the tenant against its own authorization rules before processing.
5. The logging layer reads the **verified** tenant within each service's scope.
6. If `trace_id`/`correlation_id` is present, use it to link records without treating it as proof of tenant authorization.
7. Across async/message boundaries, messages must carry sufficient designed business metadata and authorization context to be re-validated/resolved.
8. When the response finishes, the request context is closed; longer-lived callbacks or tasks must have independent scopes.

### Do Not Blindly Forward the Entire MDC Over the Network

MDC may contain `user_id`, request details, sanitized headers, or internal fields. **Do not copy the entire MDC into HTTP headers** and send them to third parties. Choose an allowlist of fields permitted to propagate, route them through an appropriate security mechanism, and know where trust boundaries lie.

## 19. Testing Against Tenant Context Leaks

Whenever changing filters, middleware, executors, or logging backends, **test both synchronous and asynchronous paths**. High-value test cases include:

| Test case | Expected behavior |
| --- | --- |
| Request A, tenant A | All tenant-scoped events carry `tenant_id=A` |
| After A, request B on **same worker** | B's events carry only `tenant_id=B`, never A |
| Request missing tenant after worker handled A | Does not inherit A; returns error or logs per auth policy |
| Exception mid-handler | `finally` still restores/clears context |
| Early return | Scope closes automatically via `try-with-resources` |
| Nested scopes A → B → A | After scope B exits, context returns to A |
| `ExecutorService` task after completion | New context does not inherit stale context |
| `CompletableFuture` with multiple callbacks | Each callback has the right tenant when needed |
| Callback running on a different thread | Tenant is not inferred from submitter's `ThreadLocal` |
| Scheduler running multi-tenant job | Per-tenant events accurate; summary does not spoof a tenant |
| Message with spoofed tenant | Untrusted metadata rejected; authorization denies |
| Request belongs to tenant A, resource belongs to B | Business layer rejects; logging context does not mask the error |
| MDC adapter/backend changed | Tenant field still appears as required by pipeline |
| JSON encoder encounters quotes/newlines | Single valid JSON event, not split into multiple events |
| Collector fails to parse MDC | Ingestion test fails early to catch the issue |
| Trace/Baggage leaves toward third party | No tenant metadata leaked against policy |
| Log viewer queries another tenant | Denied by authorization in log API/store |
| High-cardinality tenant IDs | Does not exceed limits on indexed labels/metric series |
| Async logging queue under heavy load | Tenants are not mixed across events; evaluate drops/backpressure |
| Thread context disabled at runtime | Monitoring/tests detect missing tenant fields |

### Testing a Reused Worker

Section 5 demonstrates two tenants running on a **thread pool with a single worker**. This is a highly valuable test because MDC leak bugs often remain hidden when every request gets a fresh thread, yet surface immediately when threads are reused.

### Testing Nested Scopes

Inside a method holding `TenantContext.open("tenant-A")`, open a nested `tenant-B` scope if a cross-tenant operation is genuinely authorized, then verify that when the nested scope exits, the context returns to A. Remember that **logging context restoration does not grant cross-tenant permission**; authorization and resource ownership tests remain independent.

### Testing with a Real Collector

A pattern containing `%X{tenant_id}` may display the ID in a terminal, while the collector stores it as a raw message without a dedicated field. Verify with an actual query for `tenant_id=tenant-A` and confirm the backend stores the field type, path, and access controls correctly.

## 20. Common Mistakes to Avoid

**1. Reading the tenant from a header and trusting it immediately.** Clients can spoof metadata. The tenant must be resolved/authorized from a trusted source.

**2. Using MDC as the basis for SQL authorization.** Logging context is neither a security principal nor tenant isolation.

**3. Storing the tenant in a mutable `static` variable.** Concurrent requests will overwrite each other.

**4. Failing to clear `MDC`/`ThreadContext` in `finally`.** Thread pool reuse causes subsequent requests to carry the previous request's tenant ID.

**5. Calling `MDC.putCloseable` in a nested scope and expecting it to restore the old value.** SLF4J `MDCCloseable` **removes the key** on close; it does not restore the previous value.

**6. Opening a scope on thread A and closing it on thread B.** Scopes tied to an execution context must be opened and closed in the same scope; the Java 17 example checks the owning thread.

**7. Assuming `ThreadLocal` propagates automatically through `ExecutorService`.** You must capture and apply context in the worker or use a framework propagation mechanism.

**8. Reading `ThreadLocal` when an async formatter runs.** The formatter thread may differ from the event-producing thread; capture context into the `LogEvent`.

**9. Copying the entire MDC into HTTP headers.** This can leak secrets/PII or violate trust boundaries; allowlist only required fields.

**10. Treating Baggage as proof of tenant authorization.** OpenTelemetry Baggage has no default integrity check and can come from untrusted sources.

**11. Using the tenant ID as the logger name.** This creates huge numbers of loggers; keep loggers per class/service and treat the tenant as `LogEvent` metadata.

**12. Putting the tenant into `service.name` of a shared telemetry resource.** A single instance's resource can serve multiple tenants and should not mutate per request.

**13. Making `tenant_id` an indexed label and metric dimension everywhere.** This can cause a cardinality explosion; measure and choose structured metadata/attributes appropriately.

**14. Logging customer names/emails instead of an opaque tenant ID.** This increases exposure of sensitive data and linkability to real individuals.

**15. Checking only console text for the tenant without checking the JSON collector.** The encoder may drop MDC or place the field at a different path.

**16. Attaching the current request's tenant to an entire multi-tenant batch.** Each unit of work must have its own proper scope; system-wide summaries must not spoof a tenant.

**17. Testing only happy paths and skipping exceptions/early returns/retries.** Context leaks most commonly occur on abnormal exit paths.

**18. Counting log lines per tenant as committed transactions.** Logs can be dropped, duplicated, or filtered; use official business records instead.

**19. Letting tenants query a shared index using only a UI filter.** You need server-side authorization, storage ACLs, and tests preventing cross-tenant access.

**20. Falling back to a default like `tenant-A` when the ID is empty.** Failing open to a default tenant can misassign data. For tenant-required operations, fail closed or clearly distinguish system-wide events.

## 21. Implementation Checklist for Java Applications

### A. Data Source and Authorization

- Tenant ID is determined by a **trusted resolver** after authentication/authorization.
- Access to resources belonging to the selected tenant is verified.
- Conventions exist for system events, system admins, and multi-tenant jobs.
- `MDC`/`ThreadContext` is never used as a substitute for security context.

### B. Scope and Propagation

- Tenant context is set at the request/message/job boundary after verification.
- `try/finally` or `try-with-resources` is used to restore/clear context.
- When submitting tasks, an immutable snapshot or appropriate context propagation mechanism is used.
- For reactive/virtual threads, check the framework's context model rather than relying blindly on `ThreadLocal`.
- No global mutable tenant IDs or dynamic logger names.

### C. Log Format and Collector

- `tenant_id` is emitted as a clear field whenever querying is needed.
- Values are properly typed as strings and free of CR/LF or unsafe characters.
- The encoder preserves timestamp, level, event, and trace/correlation ID.
- Structured logs have a clear schema and defined handling for missing fields.
- The collector stores the field at a consistent path; queries and alerts use the right field.
- Storage volume and index/label cardinality have been reviewed.

### D. Security and Operations

- No unnecessary secrets or PII are logged.
- Log read access is restricted per tenant when self-service log viewing exists.
- Retention, transport/storage encryption, and log-store access auditing are in place.
- Missing tenant fields on tenant-scoped events are monitored.
- Tests cover context leaks across thread pools, exceptions, retries, async boundaries, and deployments.
- Logs are not used as the guaranteed source of transaction state.

## 22. Self-Check Questions

1. **What is tenant context?** Metadata identifying the tenant of the **current unit of work**; typically attached to a `LogEvent` for diagnostics.
2. **Why shouldn't `MDC.get("tenant_id")` be used for database authorization?** MDC is mutable logging metadata, not an authenticated/authorized identity.
3. **What is a trusted source for the tenant?** The result of tenant resolution and authorization across a system boundary, not a client-supplied header.
4. **Can a `static final` logger be shared across multiple tenants?** Yes. Class-level loggers are shared; the tenant must be per-event context.
5. **Does `ThreadLocal` propagate automatically across `ExecutorService`?** No, never assume it does; capture/apply context or use a framework mechanism.
6. **Why must MDC be cleaned up when a request finishes?** To prevent a subsequent request on a reused thread from inheriting the previous tenant.
7. **Does `MDC.putCloseable` restore the previous value of a key?** Not automatically; closing removes the key. Nested scopes require manual restoration where appropriate.
8. **What can `MDC.getCopyOfContextMap()` return when there is no context?** It can return `null`; handle that case.
9. **Why shouldn't an async `Formatter` read `ThreadLocal`?** The formatter may run on a different thread from the event source.
10. **What is needed to output the tenant from Logback `PatternLayout`?** A backend supporting MDC and a pattern such as `%X{tenant_id}`.
11. **In Log4j2, which API manages the context map?** `ThreadContext`; `CloseableThreadContext` can be used for scoped management.
12. **Are `tenant_id` and `trace_id` the same?** No. Tenant describes data partitioning; trace describes execution flow.
13. **Does OpenTelemetry Baggage guarantee tamper resistance?** No; never use it as proof of tenant authorization.
14. **Should the tenant ID be placed in `service.name` for each request?** No, if the service instance serves multiple tenants; that is not the service name.
15. **Should request ID and tenant ID be added as indexed Loki labels?** Usually not for high-cardinality values; consider structured metadata or other query mechanisms.
16. **How should context be logged when a job processes multiple tenants?** Per-tenant events carry the specific tenant; summary events use system/multi scope per schema.
17. **Is a log without a tenant ID always wrong?** No. System-wide or pre-authentication events may lack a tenant; however, tenant-scoped events must include it.
18. **Is putting the tenant ID in text logs enough for the collector to query `tenant_id`?** No; the parser/encoder must store the field according to the schema.
19. **Should a request belonging to A be allowed to query B's data just because `MDC=B`?** Never; authorization and resource ownership must block this independently.
20. **Why is testing two tenants on a single worker thread useful?** It catches uncleaned scope bugs when threads are reused.
21. **Does `try-with-resources` automatically solve propagation across async callbacks?** No. Each callback/thread must open an appropriate scope.
22. **Is a `payment_completed` log line tagged with tenant A sufficient proof that transaction A succeeded?** No. Official business state is the source of truth.

## 23. References

- SLF4J `MDC` Javadoc: https://www.slf4j.org/api/org/slf4j/MDC.html
- Logback MDC manual: https://logback.qos.ch/manual/mdc.html
- Apache Log4j 2, Thread Context: https://logging.apache.org/log4j/2.x/manual/thread-context.html
- Apache Log4j 2, JSON Template Layout: https://logging.apache.org/log4j/2.x/manual/json-template-layout.html
- OpenTelemetry, Baggage and security considerations: https://opentelemetry.io/docs/concepts/signals/baggage/
- OpenTelemetry, Logs Data Model: https://opentelemetry.io/docs/specs/otel/logs/data-model/
- Grafana Loki, Labels: https://grafana.com/docs/loki/latest/get-started/labels/
- Java 17, `ThreadLocal`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html
- Java 17, `ExecutorService`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html

**Remember:** **tenant context is metadata for accurate logging, not an authorization tool**. Obtain the tenant ID from a **verified source**, place it in a **clearly scoped lifecycle**, **restore/clear** it after the request, **propagate it explicitly** across async/thread pools, and ensure your encoder/collector actually preserves the `tenant_id` field. Avoid context leaks, sensitive data exposure, and uncontrolled cardinality. Tenant access must always be protected by authentication/authorization layers and business data independent of logging.
