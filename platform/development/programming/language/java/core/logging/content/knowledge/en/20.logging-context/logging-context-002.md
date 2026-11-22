# Request Context in Java Logging: Attaching, Propagating, and Cleaning Up Per-Request Context

## 1. What is Request Context?

In a Java service handling multiple HTTP requests or messages concurrently, a standalone log call such as:

```java
log.warn("Cache miss for product {}", productId);
```

tells you **what** happened, but is not enough to answer **which request it happened in**. The same service may be processing hundreds of requests at once, with log lines from multiple threads interleaved. When investigating an issue, operators need to group events belonging to the same execution.

**Request context** is the set of information describing the execution scope of a request or unit of work, such as `request_id`, `trace_id`, `span_id`, route type, logging-approved tenant, and other technical context details. Logging context is how this information is attached to log events for filtering, correlation, and analysis.

Example of two interleaved requests:

```text
INFO  request_id=req-A event=request.received
INFO  request_id=req-B event=request.received
WARN  request_id=req-A event=inventory.cache_miss
ERROR request_id=req-B event=payment.failed
INFO  request_id=req-A event=request.completed
```

Even though the sequence is interleaved, you can filter by `request_id=req-A` to view request A's journey—no need to separate logs by thread name or guess based on timestamps.

In Java Logging, request context is typically stored in **MDC** (Mapped Diagnostic Context) when using SLF4J/Logback, or **ThreadContext** when using Log4j 2. The logging backend can include these values in text messages or JSON fields.

**The goal is not to store the entire HTTP request in logs.** Context should be *small, stable, operationally meaningful, clearly scoped in lifecycle, and free of sensitive data outside policy*.

## 2. IDs Not to Confuse

| Field | Meaning | Typical Scope | Example |
| --- | --- | --- | --- |
| `request_id` | Identifies a single request execution by system convention | One HTTP request entering a gateway/service | `req-17` |
| `trace_id` | Links operations belonging to a distributed trace | Across multiple services/processes | `4bf92f3577b34da6a3ce929d0e0e4736` |
| `span_id` | Identifies a specific span within a trace | An instrumented unit of work | `00f067aa0ba902b7` |
| `correlation_id` | Correlation ID by business/system convention | A chain of related requests or messages | `corr-42` |
| `job_id` | Identifies a job run | Batch/scheduler | `job-2026-001` |
| `message_id` | Identifies a message on a broker | Queueing system | `msg-83` |
| `event_code` | **Event type**, not a request ID | Reused across many requests | `payment.failed` |
| `order_id` | Business entity identifier | May appear across multiple requests | `O-17` |

**Request ID is not synonymous with trace ID.** A single HTTP request can create multiple spans, while a distributed trace can span cross-service requests. Many systems without full tracing still use request IDs very effectively; conversely, applications with standard tracing should reuse `trace_id` from the tracing context rather than inventing a new trace ID in every method.

**Event code is not a context ID.** `event_code=payment.failed` helps count or group *error types*; `request_id` or `trace_id` helps find *a specific instance*. If a dashboard uses request IDs as metric labels, the number of distinct values (cardinality) can grow uncontrollably.

### Fields to Consider in Context

A practical minimal set of fields:

- `request_id`: a searchable ID propagated across the request's log records.
- `trace_id` and `span_id`: only when an actual tracing context exists, using the tracing system's format.
- `service`, `environment`: usually attached by encoder/deployment configuration, not necessarily via `MDC.put` on every request.
- `http_method`: when needed for investigation, such as `GET` or `POST`.
- `http_route`: a **route template** like `/orders/{id}` rather than a raw URL containing tokens, emails, or dynamic values.
- `tenant_id`: only when permitted by data policy and after user/tenant scope has been authenticated.
- `user_id`: only when strictly necessary, with access restrictions or pseudonymization per policy.
- `operation`, `job_id`, `message_id`: for non-HTTP processing.

**There is no "the more context, the better" rule.** A context containing hundreds of fields, full request bodies, or raw headers increases overhead and data-leakage risk.

## 3. Which Layers Does Request Context Pass Through?

Consider an HTTP request arriving at a Java service:

```text
HTTP request
    |
    v
Gateway / Server filter / Interceptor
    |
    +-- Validate or generate request ID
    +-- Accept trusted tracing context
    +-- Set MDC/ThreadContext
    |
    v
Controller
    |
    +-- Log event=request.received
    |
    v
Service / Repository
    |
    +-- Log event=inventory.checked
    +-- Log event=payment.attempt_failed
    |
    +-- Async task / Executor -> requires explicit context propagation
    |
    v
Response / completion
    |
    +-- Log event=request.completed
    |
    v
finally / lifecycle hook
    |
    +-- Restore or clear request context
```

What matters is not just calling `MDC.put("request_id", value)` at the start; you must define **where the scope ends** and how context is transferred across asynchronous boundaries.

Common scenarios:

1. **One request on one thread for its entire lifecycle:** thread-bound MDC works conveniently if cleanup always runs.
2. **Request switches threads via an executor/`CompletableFuture`:** the new thread may not receive the context, requiring a propagation mechanism.
3. **Reactive frameworks:** work may hop across multiple threads, requiring a context bridge supported by the framework/instrumentation.
4. **Message consumer:** each message has its own context; it must not retain the previous message's context when the worker is reused.
5. **Scheduled job:** there is no HTTP request; use `job_id`/`operation_id` and do not fabricate a fake `request_id` field when inappropriate.
6. **One request calling another service:** correlation/tracing must be propagated over an agreed protocol; do not confuse in-JVM MDC with context transmitted over the network.

MDC is generally only a **storage mechanism for logging context within the current execution scope**, not an inter-service transport protocol, not a span by itself, and not a place to store business state.

## 4. SLF4J MDC and Logback

In code using SLF4J:

```java
import org.slf4j.MDC;

MDC.put("request_id", "req-A");
try {
    log.info("event=request.received");
    process();
} finally {
    MDC.remove("request_id");
}
```

This is an **illustrative snippet inside a method**, assuming `log` and `process()` already exist. `MDC.put` attaches a string key/value pair to the current context; a compatible logging backend can read that value when creating an event.

A common Logback pattern:

```xml
<encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
    <pattern>%level|rid=%X{request_id}|%logger{0}|%msg%n</pattern>
    <charset>UTF-8</charset>
</encoder>
```

If MDC contains `request_id=req-A`, a log line might look like:

```text
INFO|rid=req-A|OrderService|event=request.received
```

**Note:** `%X{request_id}` is layout syntax, not the `{}` parameter placeholder syntax in log messages. `%msg` outputs the event message; `%X{...}` reads from context. A message containing `order_id={}` does not automatically create an `order_id` field in MDC.

### Why Use `finally`?

Thread pools typically reuse threads. If request A sets `request_id=req-A` and fails to clean up, request B running later on the same thread may erroneously log:

```text
INFO|rid=req-A|PaymentService|event=payment.started
```

even though the event actually belongs to request B. This is **context leakage**, which corrupts investigations, audits, and trace correlation.

Cleanup must run when the request finishes **even if** the controller throws an exception, is canceled, or times out according to the framework's lifecycle. Use `try/finally` or an appropriate lifecycle hook—never clean up only on the success path.

### `remove`, `clear`, and Restoring Previous Context

- `MDC.remove("request_id")` removes only one key; suitable when you own that key and other keys must be preserved.
- `MDC.clear()` removes the entire current context map; careless use can wipe out fields set by instrumentation.
- `MDC.getCopyOfContextMap()` takes a snapshot of the current map, and may return `null` when empty.
- `MDC.setContextMap(map)` replaces the MDC map with the provided data; to return to an empty context state, use `MDC.clear()`.

If scopes can be **nested**, the safe approach is to save the previous map, set the new context inside the scope, and **restore the old snapshot** in `finally`. This prevents an inner scope from accidentally wiping out context managed by an outer scope.

Additional note: SLF4J is a facade; `MDC` operates specifically through the provider/backend adapter. Verify the actual backend and how it handles MDC. Do not assume the same `MDC.put` call produces identical output across all providers.

## 5. Complete Runnable Java 17 Example: MDC, Two Requests, and a Thread Pool

The exercise below simulates two requests processed sequentially. Each request:

1. Sets `request_id` and `trace_id`.
2. Logs a start event on the main thread.
3. Submits a task to an `ExecutorService`.
4. **Captures a snapshot and restores MDC** when the task runs on the worker thread.
5. Waits for the task to complete via `Future.get()`.
6. Logs a completion event, then **restores the pre-request context**.
7. After both requests, logs an out-of-scope event to prove there is no context leakage.

The output is designed to be deterministic: a single worker thread, waiting on `Future`, and a pattern without timestamps or thread names.

### 5.1. Maven Structure

```text
request-context-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── RequestContextDemo.java
        └── resources/
            └── logback.xml
```

Requires **JDK 17 or later**, Maven, and permission to download dependencies if not already cached.

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>request-context-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.16</version>
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

`logback-classic` provides the compatible SLF4J provider and backend. The pinned version serves **a reproducible example**, not a claim about the latest release or suitability for every framework. When adopting in a real application, check version management and current security advisories.

### 5.3. `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%level|RequestContextDemo|rid=%X{request_id}|trace=%X{trace_id}|%msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

In the pattern above, `RequestContextDemo` is a **literal string** used to make the exercise output easy to read. In production, you should usually use `%logger` or `%logger{0}` to output the real logger name rather than hard-coding a class name.

`%X{request_id}` and `%X{trace_id}` read the MDC values; when a key is absent, this pattern converter renders empty. `%msg` is the message, and `%n` appends a newline.

### 5.4. `src/main/java/demo/RequestContextDemo.java`

```java
package demo;

import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class RequestContextDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(RequestContextDemo.class);

    private RequestContextDemo() {
    }

    private static void restore(Map<String, String> snapshot) {
        if (snapshot == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(snapshot);
        }
    }

    private static Runnable propagate(Runnable action) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous =
                    MDC.getCopyOfContextMap();
            try {
                restore(captured);
                action.run();
            } finally {
                restore(previous);
            }
        };
    }

    private static void handleRequest(
            ExecutorService pool,
            String requestId,
            String traceId) throws Exception {

        Map<String, String> previous =
                MDC.getCopyOfContextMap();

        try {
            MDC.put("request_id", requestId);
            MDC.put("trace_id", traceId);

            LOG.info("event=request.started");

            Future<?> task = pool.submit(propagate(() ->
                    LOG.info("event=inventory.checked")));
            task.get();

            LOG.info("event=request.completed");
        } finally {
            restore(previous);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool =
                Executors.newSingleThreadExecutor();

        try {
            handleRequest(pool, "req-A", "trace-A");
            handleRequest(pool, "req-B", "trace-B");
            LOG.info("event=outside.request");
        } finally {
            pool.shutdown();
        }
    }
}
```

### 5.5. Compile, Run, and Stdout

From the `request-context-demo` directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.RequestContextDemo
```

**Seven lines emitted by the application's Logback configuration:**

```text
INFO|RequestContextDemo|rid=req-A|trace=trace-A|event=request.started
INFO|RequestContextDemo|rid=req-A|trace=trace-A|event=inventory.checked
INFO|RequestContextDemo|rid=req-A|trace=trace-A|event=request.completed
INFO|RequestContextDemo|rid=req-B|trace=trace-B|event=request.started
INFO|RequestContextDemo|rid=req-B|trace=trace-B|event=inventory.checked
INFO|RequestContextDemo|rid=req-B|trace=trace-B|event=request.completed
INFO|RequestContextDemo|rid=|trace=|event=outside.request
```

Maven may print its own output; this is the **application's logging output** when the `logback.xml` above is loaded and no competing backend/provider is present.

### 5.6. Why This Example Is Correct

- `MDC.put` sets the two keys on the request-handling thread; the two main events of each request receive their corresponding context.
- `propagate` **captures a snapshot at the time the `Runnable` is created**, before submitting it to the pool. It does not directly use a shared map that might be mutated later.
- On the worker thread, `propagate` saves the previous MDC, applies the request's context, runs the task, and restores the previous MDC in `finally`. When the worker is reused for the next request, it no longer carries `req-A`.
- `Future.get()` waits for the task to finish before logging `request.completed`, making the demo's output order predictable.
- `handleRequest` saves and restores the calling thread's MDC; if an outer layer has already set another context, it is not wiped out just because a request scope ends.
- After both requests, `event=outside.request` has both fields empty, demonstrating there is no **context leakage** on the main thread.

**Limitation:** this example illustrates snapshot-based propagation for a `Runnable`. In real applications, executors also receive `Callable`, nested tasks, cancellations, and framework integrations; use your framework/instrumentation's context propagation mechanism or complete wrappers for real code paths. Do not copy a hand-rolled wrapper to replace an entire tracing system if context management tooling is already available.

## 6. Why `ThreadLocal` Does Not Automatically Solve Async Propagation

Many Java backend MDC implementations store data in a **thread-local**-like scope. Key principle:

**Data on thread A does not automatically and safely appear on thread B when A calls `executor.submit(...)`.**

Example of a wrong expectation:

```java
MDC.put("request_id", "req-A");

executor.submit(() -> {
    log.info("event=work.started");
});
```

This is an **illustrative snippet**. The logger inside the task may lack `request_id` because the task runs on a different thread. Depending on the implementation/framework, it might also carry stale context left over from a thread pool worker that was not cleaned up.

### Do Not Use `InheritableThreadLocal` as a General Solution

`InheritableThreadLocal` copies values when a child thread is created, but executors typically **reuse** threads; a worker may have been created long before the request started. Inheritance at thread creation time does not guarantee the right context for each task submitted later.

Therefore, even if a backend has a mechanism to copy context to child threads, **do not assume it works correctly with thread pools**. Test it with two consecutive requests on the same worker thread.

### Snapshot on Submit, Restore on Run

Safe rule for `Runnable`/`Callable`:

1. Capture the context snapshot on the **submitting thread**.
2. Pass the snapshot through the submission path or official propagation API.
3. When the worker is about to run, save the worker's previous context.
4. Apply the snapshot for the duration of task execution.
5. In `finally`, restore the worker's previous context.
6. When the task finishes, the worker thread retains no context from that request.

Do not blindly call `MDC.clear()` at the end of a worker in all cases: if a framework set valid context before the task, clearing everything can break its data. **Restoring the previous snapshot** is safer when scopes can be nested.

### `CompletableFuture` and Parallel Streams

Code like:

```java
CompletableFuture.supplyAsync(() -> service.fetch(id));
```

may run on a custom executor or the common pool, depending on the overload and usage. Do not assume MDC follows the request just because the task was created from a request thread. With `CompletableFuture`, use wrappers/explicit executors and propagate at **every relevant scheduling boundary**, not only the first step.

Parallel streams may use multiple workers; relying on a single thread-bound MDC easily leads to missing or mixed-up context in logs. If business logic requires correlation, pass IDs in the task data or integrate tested context propagation.

### Reactive Pipelines and Virtual Threads

In Reactor/WebFlux and reactive systems, callbacks may switch threads multiple times; request context usually needs to be managed via **Reactor Context or an integrated context propagation mechanism**, not just a single `MDC.put` at the HTTP entry point.

Virtual threads appeared in Java versions after JDK 17 (not an API available in the Java 17 example), yet **changing the thread model alone does not solve context propagation across independent tasks**. Whether using platform threads or virtual threads, lifecycle, propagation, and cleanup still require explicit design.

There is no universal "MDC automatically works in every async framework" guarantee.

## 7. Applying at the HTTP Boundary with a Servlet Filter

In a Jakarta Servlet application, a convenient place to set context is a filter wrapping the request. The example below is an **illustrative snippet** requiring the Jakarta Servlet API, a servlet container/framework, and SLF4J; it is **not part of the standalone Maven project in Section 5**.

```java
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.MDC;

import java.io.IOException;
import java.util.Map;
import java.util.UUID;

public final class RequestIdFilter implements Filter {
    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        HttpServletRequest http = (HttpServletRequest) request;
        String incoming = http.getHeader("X-Request-ID");

        String requestId = isAllowedId(incoming)
                ? incoming
                : UUID.randomUUID().toString();

        Map<String, String> previous =
                MDC.getCopyOfContextMap();

        try {
            MDC.put("request_id", requestId);
            MDC.put("http_method", http.getMethod());
            chain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    }

    private static boolean isAllowedId(String value) {
        return value != null
                && value.length() >= 1
                && value.length() <= 64
                && value.matches("[A-Za-z0-9._-]+");
    }
}
```

### What to Consider Before Production Use

- **Do not trust every header from clients.** `X-Request-ID` in the example is an application convention; a system may choose to accept, replace, or prioritize IDs issued by a trusted gateway. The rules must be defined and consistent across services.
- **Restrict format and length** to prevent newline/log injection and oversized junk data. The example regex is just a simple allowlist, not a standard trace ID format.
- **Do not log raw URLs containing personal data or tokens.** If you want the route, use the post-routing route template or framework-normalized metadata.
- **Do not assume a single `try/finally` in a synchronous filter covers async request handling.** If the application uses Servlet async dispatch or completes the response after the initial thread exits the filter, attach context on the subsequent lifecycle callbacks/dispatches and clean up at the right time.
- **Do not cast every `ServletRequest` to `HttpServletRequest`** in a filter intended for multiple protocols; the example is for HTTP applications only.
- **Do not treat a header ID as proof of authentication.** An ID correlates logs; it does not prove who the caller is.
- **Do not generate a UUID for `trace_id` if tracing uses a different standard format.** Obtain it from the tracing instrumentation.

In real projects, filter registration, filter ordering, response headers, and status code retrieval depend on the framework. A framework with built-in request correlation/tracing may already provide a filter/interceptor; **check before writing another** to avoid two layers assigning different IDs or logging twice.

### Returning Request ID to the Client

Some APIs return a correlation ID in a response header so support teams can locate logs when a user reports an error. If you do this, standardize the header name and format, and do not expose IDs containing private data or sensitive information. The ID remains only a lookup key—it **does not grant log access** to whoever holds it.

## 8. From an HTTP Request to Calling Another Service

Suppose service A receives a request and calls service B:

```text
Client -> Gateway -> Service A -> Service B -> Database
            |             |            |
            v             v            v
        request ID    trace/span    trace/span
```

Calling `MDC.put` in service A **does not automatically send data to B**. Context must be propagated via HTTP headers or protocol metadata according to an agreed contract.

Two common strategies:

- **Dedicated request/correlation ID:** the gateway/service sets a header such as `X-Request-ID` per internal contract; downstream services validate and use or replace it according to trust policy.
- **Standard distributed tracing:** instrumentation extracts/injects W3C Trace Context via `traceparent` and related fields, and the logging backend reads `trace_id`/`span_id` from the active span.

Do not write half-baked regexes to parse `traceparent` and swap it with arbitrary strings. W3C Trace Context has its own format and validation rules; prefer supported tracing SDKs/instrumentation to create, extract, and propagate it. For headers from untrusted sources, enforce trust-boundary policies and metadata limits.

When downstream returns an error, logs in A and B may share the same `trace_id` while each service has a different `span_id`. This is **correct behavior** in tracing, not a mismatch.

### Why Propagating Only a Request ID Is Not Enough

A request ID enables lookup by a single ID, but does not by itself provide:

- Span hierarchy and per-step timing.
- Parent/child relationships.
- Cross-service latency analysis.
- Trace sampling decisions.
- Baggage propagation and trust boundaries.

If you need those capabilities, use a proper tracing system. Logging request context complements distributed tracing: **logs provide event details**, while traces capture relationships and timing across steps.

## 9. Message Consumers and Scheduled Jobs Also Have Context

Not all work originates from HTTP.

### Message Consumers

A message may carry `message_id`, `correlation_id`, and `traceparent` in headers or metadata. When a consumer receives a message:

1. Validate incoming context data from the broker or producer according to policy.
2. Set context for **a single message processing attempt**.
3. Log start, success, and failure/retry events with clear `event_code` values.
4. When calling other services or publishing new messages, propagate context appropriately.
5. Clean up in `finally` before the worker receives the next message.

**Illustrative snippet:**

```java
Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.put("message_id", messageId);
    MDC.put("correlation_id", correlationId);
    consumerService.handle(message);
} finally {
    if (previous == null) MDC.clear();
    else MDC.setContextMap(previous);
}
```

The snippet above assumes `messageId`, `correlationId`, `consumerService`, and `message` already exist; it is not a standalone program.

**Retrying a message** may share the same `message_id` or `correlation_id`, while each retry is a distinct attempt. Separate `attempt` and `event_code` so multiple log records are not mistaken for multiple business messages.

### Scheduled Jobs

A batch job should have a meaningful `job_id`, `job_run_id`, or `operation_id`. Do not set `request_id=unknown` for every job just to fill a column: when multiple jobs run concurrently, `unknown` does not help investigation.

Example:

```text
INFO job_run_id=run-81 event=job.started
INFO job_run_id=run-81 event=batch.processed count=100
INFO job_run_id=run-81 event=job.completed
```

When a job runs multiple tasks in parallel, use the same snapshot/propagation mechanism appropriate for async tasks, and log `task_id`/`partition` when needed to distinguish them.

## 10. Request Context in Log4j 2: ThreadContext

Log4j 2 provides `ThreadContext` to store a context map and stack. It serves a similar purpose to SLF4J's MDC, but is a **separate API and implementation**.

```java
import org.apache.logging.log4j.ThreadContext;

ThreadContext.put("request_id", requestId);
try {
    log.info("event=request.received");
} finally {
    ThreadContext.remove("request_id");
}
```

This is an illustrative snippet inside a method that already has a logger and `requestId`. A Log4j 2 pattern might be:

```xml
<PatternLayout
    pattern="%level|rid=%X{request_id}|%c{1}|%m%n"
    charset="UTF-8" />
```

The `PatternLayout` element belongs to Log4j 2 and must be placed inside an appropriate appender in `log4j2.xml`. It is not a Logback configuration file.

### Scoping with CloseableThreadContext

Log4j 2 supports a scoped context helper:

```java
import org.apache.logging.log4j.CloseableThreadContext;

try (CloseableThreadContext.Instance scope =
        CloseableThreadContext.put("request_id", requestId)) {
    log.info("event=request.started");
}
```

This is an illustrative snippet assuming `requestId` and a Log4j 2 logger are present. `try-with-resources` closes the scope even when an exception occurs. Check the semantics of other context keys in your version and setup; do not assume thread pools automatically propagate context just because you use a scoped helper.

### Propagating ThreadContext Across Executors

Just like MDC, you must snapshot the context map on the submitting thread, apply it on the worker, and restore the previous context when the task ends. Log4j 2 has corresponding snapshot/context-data APIs; **do not copy `org.slf4j.MDC` into Log4j 2 code without understanding the bridge/provider direction**.

If you use the SLF4J API bridged to a Log4j 2 backend, verify how MDC interacts with the active provider. Do not assume calling both `MDC.put` and `ThreadContext.put` is always necessary or never overlaps; choose one consistent management API according to your architecture.

## 11. Request Context and Structured Logging

Text patterns help human readers:

```text
INFO rid=req-A trace=trace-A event=inventory.checked
```

For centralized analysis systems, however, it is usually more useful to store each field separately:

```json
{
  "timestamp": "2026-01-01T00:00:00Z",
  "level": "INFO",
  "service": "inventory",
  "event_code": "inventory.checked",
  "request_id": "req-A",
  "trace_id": "trace-A",
  "message": "Kiểm tra tồn kho hoàn tất"
}
```

This is an **illustrative schema**. `trace-A` is only a placeholder value for learning log correlation—**not a valid W3C trace ID**.

Key distinctions:

- `MDC.put("request_id", ...)` adds context to the scope.
- `log.atInfo().addKeyValue("event_code", ...)` attaches a field to **a single event** when using SLF4J 2.x.
- The encoder/JSON layout reads data from the event and produces JSON.
- The collector/indexer ingests the JSON and indexes the fields.

With SLF4J 2.x:

```java
log.atInfo()
        .addKeyValue("event_code", "inventory.checked")
        .addKeyValue("sku", sku)
        .log("Đã kiểm tra tồn kho");
```

This is an illustrative snippet. `event_code` and `sku` are per-event fields; `request_id` from MDC can be emitted alongside them if the encoder supports it. **Not every `PatternLayout` automatically converts them to JSON**, and not every backend prints key-value pairs unless configured.

### Which Fields Belong in MDC vs. on the Event?

A useful design rule:

| Context | Where to Place It? | Why? |
| --- | --- | --- |
| `request_id` | MDC/ThreadContext | Repeats across many logs of a single execution |
| `trace_id`, `span_id` | Instrumentation/MDC context | Correlates multiple events |
| `service`, `environment` | Encoder/deployment configuration | Constant within the same process |
| `event_code` | Field on each log event | Each event has its own meaning |
| `order_id` | Event field or intentionally narrow-scoped context | Not every event in the service relates to an order |
| `error_code`, `attempt`, `duration_ms` | Field on each event | Varies per event |
| `http_route` | Normalized context | Same route during a request, but avoid raw URLs |

There is no rigid rule for every application; what matters is that **the scope of the data matches the scope of its use**. Putting `order_id` into thread-wide MDC too early can cause unrelated events to accidentally carry an old order ID.

## 12. Security and Privacy of Request Context

Request context makes tracing easier, but it also makes data easier to search. Things you should not put into MDC or logs:

- Passwords, session tokens, API keys, bearer tokens, cookies.
- The `Authorization` header or full request headers unless controlled.
- Full request/response bodies containing personal data.
- Raw URLs/query strings with emails, verification codes, or payment details.
- Card data, national ID numbers, and health information when not permitted.
- Objects whose `toString()` accidentally exposes secrets.
- Unvalidated context values that may contain newlines or control characters.

### Untrusted `X-Request-ID` Input

If an application accepts IDs from external callers, a sender could supply:

```text
req-1
ERROR admin-auth-success
```

This is an example of **log injection** caused by a value containing a newline. Inserting it verbatim into a text pattern can produce output that looks like two separate log records.

Prevention:

1. Accept headers only at a defined trust boundary.
2. Restrict **length, character set, and count** of context entries.
3. When invalid, generate a new ID per policy instead of logging the malicious string verbatim.
4. Use an encoder with proper escaping, especially when emitting JSON Lines.
5. Never treat an ID in logs as proof of an authenticated user.
6. Review centralized log read permissions and retention.

### Tenant and User Context

`tenant_id` and `user_id` can be personal data or tied to access control. If needed for investigation, prefer server-authenticated IDs rather than an unverified client `X-Tenant-ID`. Just because an ID looks opaque **does not mean** it can be stored or queried without limits; follow data and retention policies.

### Do Not Use Context as Business State Storage

MDC is suited for small strings for observability, not for storing sessions, permissions, or payment decisions. Do not rely on `MDC.get("tenant_id")` for authorization when the source of truth for the tenant lives in a separate security context. Logging context can be missing or altered during propagation and is not a trusted security channel.

## 13. Performance: Context Must Not Add Excessive Overhead

Every log emission may snapshot MDC, format fields, encode UTF-8/JSON, and write to an appender. If the context holds dozens of large fields, every log event can carry unnecessary data.

Recommendations:

1. Keep context small: short IDs, route templates, essential technical metadata.
2. Use simple string/field values; avoid serializing entire domain objects into MDC.
3. Do not generate a new `request_id` on every log line; create it once at the processing boundary.
4. Do not enable broad DEBUG/TRACE logging just to capture trace IDs; attach context to existing INFO/WARN/ERROR events.
5. Do not use `request_id`/`trace_id` as high-cardinality metric labels; store them in appropriate logs/traces.
6. With async logging backends, understand when the backend **captures** MDC into the event and when the encoder writes it. Test in practice rather than assuming context is read at the same moment across all backends.
7. When wrapping every `submit` for propagation, consider map-copying cost and task volume; monitor performance on hot paths.
8. Do not push large-payload context into downstream service headers; propagate only keys allowed by contract.

**Calling a log method is not the same as persisting the log.** Correct context does not prevent log loss caused by full appender queues, slow collectors, full disks, or container restarts. For critical business events requiring exact delivery counts, design a dedicated reliable recording/delivery mechanism.

## 14. Testing Request Context: Preventing Cross-Request Leakage Is Priority One

A good test checks not only that a log contains `request_id`, but also proves **context does not leak into another request**.

### Recommended Test Matrix

| Scenario | Expected Outcome |
| --- | --- |
| Request A hits logger | All required events carry `request_id=A` |
| Request B on same thread after A | No event from B carries A |
| Executor task from A | Task events carry A's context if propagation is designed |
| Executor task from B after A | Task events carry B, no longer A |
| Task without request context | No leftover ID from a previous request |
| Nested scope with new key | After exit, parent scope context is restored |
| Exception in controller/service | Cleanup runs even on the error path |
| Async task timeout/cancellation | Canceled task does not leave stale context on the worker |
| Tracing bridge with trace/span | Event IDs match the active span |
| Malformed input header | Rejected/replaced, no log injection |
| JSON log output | `request_id` is a distinct field with consistent type across events |
| Multi-tenant request | Does not log the previous request's tenant |
| No provider/encoder mismatch | Configuration actually loads and fields appear in output |
| Two services | Context propagates via headers/instrumentation |

### Testing Layer 1: Context Data

You can assert `MDC.get("request_id")` within the active scope and verify it returns to its previous state in `finally`. This tests JVM **state**, but does not prove the appender actually wrote the field.

### Testing Layer 2: Logging Events

With Logback, `ListAppender<ILoggingEvent>` can capture logging events to inspect:

- `getLoggerName()`, `getLevel()`, `getFormattedMessage()`.
- `getMDCPropertyMap()` containing the event's request ID at the time it was logged.
- `getThrowableProxy()` when testing errors.
- The count of each `event_code` within a request.

Detach/stop the test appender and revert logger settings after the test. Avoid mutating JVM-wide logger configuration in parallel tests without isolation.

**`ListAppender` does not prove the console/JSON encoder emitted the exact bytes.** When you need to verify actual output, run a subprocess or an appender test with the real encoder.

### Testing Layer 3: Console/JSON

With the text pattern from Section 5, you can compare the seven log lines with their exact IDs. With a JSON encoder:

- Parse each JSON object using a reliable JSON library.
- Assert `request_id`, `trace_id`, `event_code`, level, and logger against the schema.
- Assert fields are **absent or null/empty** per contract when outside a request.
- Test that newlines, quotes, and Unicode in messages do not break JSON Lines boundaries.
- Verify malformed IDs are rejected/normalized appropriately.
- Ensure no fake sensitive data appears in any field, message, or exception.

### Testing Layer 4: Collector and Multiple Services

In staging, send a test request with a safe correlation ID across two services and search the central store:

1. All events can be found by `trace_id` or `request_id` per contract.
2. Events from each service have the correct `service` and logger.
3. Trace/span relationships are valid when using distributed tracing.
4. No events from other requests are tagged with the wrong ID.
5. No duplicate records due to appender/additivity or out-of-policy collector retries.
6. No missing events due to log levels/filters, queues, sampling, or ingest errors.
7. Queries have appropriate time ranges and read permissions.

## 15. Diagnosing Missing Request Context

Work from source to destination:

```text
Is a request/correlation ID created?
     |
     +-- No -> Check gateway/filter/interceptor
     |
     +-- Yes -> Was it placed into MDC/ThreadContext in the right scope?
                     |
                     +-- No -> Check lifecycle entry/exit
                     |
                     +-- Yes -> Did execution switch threads or processes?
                                   |
                                   +-- Yes -> Check propagation
                                   |
                                   v
                             Does the logging event have the context?
                                   |
                                   +-- No -> Check backend/provider/bridge
                                   |
                                   v
                             Does the encoder output the context?
                                   |
                                   +-- No -> Pattern %X / JSON field mapping
                                   |
                                   v
                             Does the collector keep and index the field?
                                   |
                                   +-- No -> Parser, mapping, filter, retention
                                   |
                                   v
                             Is the query filtering the right time range and service?
```

### Common Issues

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Controller logs have ID, executor logs do not | MDC does not auto-propagate to worker threads | Snapshot on submit, apply/restore on worker, or use framework propagation. |
| Request B events carry A's ID | Missing cleanup in thread pool | `try/finally` and restore previous context. |
| `rid=` is empty | MDC not set or wrong key in pattern | Check `request_id` vs `requestId`, scope, and provider. |
| Context lost after nested call | Inner scope called `MDC.clear()` | Snapshot before scope and restore after scope. |
| Service B logs lack trace ID | MDC only set in service A | Propagate HTTP/message context via SDK/instrumentation. |
| Two different trace IDs on the same request | Gateway/framework and filter generate IDs independently | Decide ownership and trust/propagation rules. |
| ID value contains newlines | Trusting raw client header | Validate length/characters and encode properly. |
| MDC is set, but JSON lacks the field | Encoder/provider does not emit MDC or mapping is wrong | Check actual JSON encoder/collector configuration. |
| Context has ID, but message output lacks it | Pattern only prints `%msg` without `%X` | Add the appropriate converter/context provider. |
| No logs in collector | Logger level, appender, stdout/file, collector, or retention | Inspect the pipeline; context does not generate logs by itself. |
| Tenant ID mixed up across requests | Thread reuse, faulty cleanup, or wrong source data | Authenticate tenant source and restore context on all paths. |
| Single-threaded tests pass, production mixes context | Async/reactive code or different filter lifecycle | Test executor reuse/cancellation and integration in real runtime. |
| Trace appears in message text, but field cannot be filtered | ID only concatenated into text | Use structured logging/encoder and field mapping. |
| Metrics have too many labels | Using request ID as a metric label | Group by `event_code`, `service`, `result`; look up IDs in logs. |
| Event reported as ERROR multiple times | Multiple layers log the same exception | Define a single failure boundary and event code. |

## 16. Gradual Adoption in a Running Application

A safe rollout path:

1. **Choose ID rules:** which IDs the gateway issues, which the tracing SDK issues; limits and trust boundaries.
2. **Define context owners:** filter/interceptor for HTTP, consumer wrapper for messages, job runner for batch.
3. **Establish lifecycle:** snapshot before request, set context, run business logic, cleanup/restore in `finally`.
4. **Inventory async boundaries:** executors, `CompletableFuture`, callbacks, Reactor, message queues, scheduled tasks; each needs its own propagation path.
5. **Standardize schema:** `request_id`/`trace_id`/`span_id` share the same names and types across all services.
6. **Configure backend:** Logback `%X{request_id}` or JSON encoder; corresponding Log4j 2 `ThreadContext`/JSON template.
7. **Add event codes:** enable searching events by type without parsing message prose.
8. **Security review:** allowlists and limits on dynamic data; keep tokens, raw URLs, and PII out of context.
9. **Test two requests on the same worker:** intentionally reuse a thread to catch leaks.
10. **Test exceptions/cancellation:** prove cleanup still runs.
11. **End-to-end test:** HTTP A → B, async tasks, JSON collector; query by trace/request ID.
12. **Canary and monitor:** percentage of logs missing IDs, context mismatch errors, encoder overhead, and cardinality.
13. **Controlled rollback:** if schema/collector issues arise, revert to the previous pattern without changing business logic.

### What to Check When Upgrading Frameworks

Your framework or instrumentation may already manage MDC/tracing. Before adding a new filter, check:

- Are `trace_id`/`span_id` already set automatically?
- Which gateway/header request IDs are accepted?
- Are there hooks to set and clean up context on async dispatches?
- Is the encoder configured to output MDC/ThreadContext as JSON?
- Is there a risk of two filters using the same key with different IDs?

Integrating with your framework's built-in mechanisms prevents competing request-context systems and reduces custom code with subtle bugs.

## 17. Practice Exercises

### Exercise 1 — Identify the Field

Among the following values, which fields are for **grouping by event type**, and which are for **tracing a single request**?

```text
event_code=payment.failed
request_id=req-81
trace_id=4bf92f3577b34da6a3ce929d0e0e4736
error_code=GATEWAY_TIMEOUT
```

**Answer:** `event_code` and `error_code` are suitable for grouping event/error types when the catalog is bounded; `request_id` and `trace_id` are for tracing a single execution or distributed trace. Do not use dynamic IDs as unbounded metric labels.

### Exercise 2 — Thread Pool Bug

Request A calls `MDC.put("request_id", "A")` and then `executor.submit`. The task running on the worker does not have `request_id`. Why?

**Answer:** MDC bound to the current scope/thread does not automatically propagate to executor workers. Capture a context snapshot at submission time, pass it via a supported propagation API, apply it on the worker, and restore in `finally`.

### Exercise 3 — ID Mix-Up Between Two Requests

Request A and request B are processed sequentially on the same worker. B has logs carrying A's ID.

**Answer:** Inspect A's cleanup, how scopes terminate on exceptions/timeouts, and whether the worker retains stale `ThreadLocal`/MDC state. Test two consecutive requests with a single-thread pool and assert no record from B carries A.

### Exercise 4 — `clear` or `restore`?

A helper method needs to set its own `operation_id`, but calls `MDC.clear()` upon exit. Why is this bad?

**Answer:** It can wipe out `request_id` and `trace_id` from the parent scope. Save the context before entering the scope and restore it after completion, or only `remove` the key you own if nested replacement is not needed.

### Exercise 5 — Untrusted HTTP Header

A client sends an `X-Request-ID` tens of thousands of characters long, containing newlines and tokens. Should this header be logged verbatim as the ID?

**Answer:** No. Enforce length/character-set limits, define a trust boundary, generate a new ID if invalid, and do not print malicious headers; ensure encoder escaping and keep secrets out of logs.

### Exercise 6 — How Does Trace ID Differ from Request ID?

Service A calls B and C; each service may receive a different internal request ID while sharing the same trace ID. Is this a bug?

**Answer:** Not necessarily. `trace_id` can span the entire distributed journey, whereas a contract-specific request ID may exist only at a gateway/hop. If you want a single ID propagated end-to-end, establish a unified propagation policy; do not force the two ID types into one.

### Exercise 7 — Proving No Context Leakage

In the Maven program from Section 5, explain why the last line has `rid=|trace=` and how to strengthen the test to catch bugs.

**Answer:** `handleRequest` restores the pre-scope MDC, so after both runs there is no request context left on the main thread. The last line is an out-of-request event. You can add assertions in an appender test on `getMDCPropertyMap()` and submit an out-of-request task to the same worker to prove the worker does not retain old IDs either.

### Exercise 8 — Structured Logging

An application uses `%msg%n` and calls `MDC.put("request_id","req-A")`, but the log store has no `request_id` field. What should be done?

**Answer:** MDC is not printed automatically when the pattern omits `%X` and the JSON encoder is not configured. Add the `%X{request_id}` converter for text or configure the JSON encoder to emit MDC as separate fields; verify output after ingestion.

### Exercise 9 — Message Consumer

A message is retried three times. All retries share the same `message_id` while `attempt` increments. Are these three distinct business messages?

**Answer:** Not necessarily. `message_id` identifies the message per broker/application; `attempt` describes the processing attempt count. Distinguish between `attempt_failed` and final `processing_failed` events if you want to count failed messages.

## 18. Pre-Production Request Context Checklist

- [ ] Know which IDs are request, trace, span, correlation, and event; do not mix them up.
- [ ] Have a clear owner that creates/accepts request IDs at the system boundary.
- [ ] Validate client headers and never treat them as an authentication source.
- [ ] Keep context limited to small, permitted key-value pairs with stable formats.
- [ ] Set context before business processing, and clean up or restore in `finally`.
- [ ] Nested scopes do not accidentally erase parent-scope context.
- [ ] Tasks via executors/`CompletableFuture` are propagated and restored properly.
- [ ] Reactive/message/scheduler flows have their own lifecycle and propagation.
- [ ] Downstream services receive tracing/correlation via an appropriate protocol, not cross-JVM MDC.
- [ ] The logging backend/provider actually supports MDC/ThreadContext.
- [ ] Text patterns or JSON encoders emit the context fields accurately.
- [ ] All required events have appropriate event codes/levels and request/trace IDs.
- [ ] Test two consecutive requests on the same worker, plus exceptions and cancellations.
- [ ] Test that logs outside a request contain no stale IDs.
- [ ] Keep raw URLs, tokens, cookies, and sensitive data out of MDC.
- [ ] JSON encoding handles newlines, quotes, and Unicode safely.
- [ ] The collector can query trace/request IDs across services, with proper retention and read permissions.
- [ ] Metrics do not use dynamic IDs as unbounded-cardinality labels.
- [ ] Logging context is not used for security or business decisions.
- [ ] Ability to verify and roll back if schema or propagation changes.

**Conclusion:** Request context turns scattered log records into a traceable journey. The focus is not merely `MDC.put`, but **setting context at the right boundary → propagating across async and network calls → attaching fields to events → cleaning up/restoring on every path → verifying output and collector ingestion**. When scope and lifecycle are well designed, Java logs support effective investigation without mixing data across requests.