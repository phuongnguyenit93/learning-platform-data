# Practice Project: Adding MDC to Java Core Logging

## 1. Problem Statement and Goals

A Java application processes many HTTP requests, messages, or background tasks concurrently. Log lines like `"Order received"` or `"Payment failed"` are usually not enough to tell which request a record belongs to, which tenant it is for, or whether it is related to logs on a worker thread. Concatenating `requestId` manually into every `logger.info(...)` call makes it easy to miss a field or copy the wrong ID.

**MDC — Mapped Diagnostic Context** is a key–value map attached to the **thread's execution context** that the logging backend can use to enrich every log event. With SLF4J and Logback, your code can call `MDC.put("requestId", ...)` once at the boundary, and then configure Logback to use `%X{requestId}` to output the value on every log line within that scope.

This practice exercise builds **a Maven project running on Java 17**, adding:

- `requestId`: a request identifier for looking up logs belonging to the same operation.
- `tenantRef`: a mock tenant identifier already verified by the system (not a token or authorization proof).
- A `try/finally` scope: guarantees MDC restoration even when an exception occurs.
- A wrapper to propagate an MDC snapshot when submitting tasks to an `ExecutorService`.
- A task with no request context to verify **no MDC leakage** from a previous task.
- A `logback.xml` configuration using the `%X{key:-default}` pattern and JUnit tests to verify propagation and cleanup.

**After this lesson**, you will know how to add MDC to a real logger, understand the difference between per-thread context and cross-service context, fix the "request B inherits A's requestId" bug, and verify behavior from actual output rather than guesswork.

> **Scope:** This project genuinely uses `org.slf4j.MDC` + `logback-classic`. It does not use a custom `ThreadLocal` in place of MDC. IDs such as `req-A` or `tenant-1` are **hardcoded mock data** so that run results are reproducible; in production, they must come from a trusted boundary.

## 2. Background: MDC and Message Templates

### A Log Call Before and After MDC

Before:

~~~java
LOG.info("event=order_processed");
~~~

The output might be:

~~~text
event=order_processed
~~~

Once MDC contains `requestId=req-A` and `tenantRef=tenant-1`, the log call **does not need to change**, yet the encoder can output:

~~~text
event=order_processed requestId=req-A tenantRef=tenant-1
~~~

MDC **does not alter the business event**, does not turn an error into a success, and does not replace event-specific fields (`errorCode`, `durationMs`, `orderRef`, etc.). It enriches logs with metadata belonging to the **processing scope**.

### Three Data Sources to Distinguish

| Source | Examples | Appropriate Usage |
| --- | --- | --- |
| **MDC request/message scope** | `requestId`, `tenantRef`, `correlationId` | Same value across multiple logs within one scope |
| **Event attributes** | `event`, `errorCode`, `outcome`, `durationMs` | Fields specific to a single log call; SLF4J 2.x supports `addKeyValue` |
| **Resource/deployment** | `service.name`, `service.version`, environment | Usually comes from deployment/telemetry resource configuration, not the request |

`MDC.put` does not emit a log by itself: it only modifies the thread's map. `%X{requestId}` in a pattern does not generate a new ID: it only reads the value if the backend supports MDC and the code has set the field. Logback's MDC is fundamentally **not automatically propagated to child threads or thread pools**. When submitting tasks through an executor, the application must use a wrapper or framework propagation mechanism.

### When Should You Use MDC?

Use MDC when multiple events within the **same scope** should carry the same fields: `requestId`, `correlationId`, `traceId`/`spanId` provided by tracing instrumentation, verified `tenantRef`, or `jobId`. Do not put full request bodies, HTTP headers, secrets, or object `toString()` outputs into MDC.

If only a single event needs `errorCode=PAY-TIMEOUT`, consider using an **event key–value** instead of putting `errorCode` into MDC and forgetting to clear it, which would cause a subsequent success event to carry the old error.

## 3. Tooling and Project Structure

Requirements: **JDK 17+**, **Apache Maven 3.9+** (or a version compatible with the plugins), a terminal, and an editor. Verify with:

~~~bash
java -version
javac -version
mvn -version
~~~

Sample directory layout:

~~~text
mdc-practice/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── demo/logging/mdc/
    │   │       └── MdcProject.java
    │   └── resources/
    │       └── logback.xml
    └── test/
        └── java/
            └── demo/logging/mdc/
                └── MdcProjectTest.java
~~~

Create an empty Maven project, create the exact paths above, and copy in the contents below. These are **four standalone, ready-to-use files** when placed in the right locations, not partial snippets missing classes.

**Versions used in this sample** are pinned for reproducible behavior: SLF4J API 2.0.20, Logback Classic 1.6.6, JUnit Jupiter 5.12.2, Maven Compiler Plugin 3.14.1, Surefire 3.6.1, and Exec Maven Plugin 3.5.1. SLF4J 2.x is compatible with Logback 1.6.x; Logback 1.6.x requires Java 11+, so Java 17 works. When adopting this in a real application, apply patches and check CVEs/compatibility against your organization's dependency management; do not downgrade Logback just to copy an older example.

## 4. File 1 — `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo.logging</groupId>
    <artifactId>mdc-practice</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.20</version>
        </dependency>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.6.6</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.12.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Dependency explanation:**

- `slf4j-api` is the logger and MDC API (`Logger`, `LoggerFactory`, `MDC`).
- `logback-classic` is **an SLF4J provider/backend** that stores and outputs MDC via patterns. Maven automatically pulls in `logback-core` and matching transitive dependencies. Do not add another SLF4J provider to the same runtime unless intentionally required.
- `junit-jupiter` provides the test lifecycle. `maven-surefire-plugin` runs JUnit when executing `mvn test`.
- `maven-compiler-plugin` with `release=17` targets Java 17 source and bytecode; a compatible JDK must still be installed on the machine.
- `exec-maven-plugin` lets you run the main class directly through Maven; there is no need to build a fat JAR for this exercise.

When integrating into Spring Boot or a framework with dependency management, **prefer the BOM/dependency versions managed by the framework** if compatible. Do not add multiple versions of SLF4J/Logback, which can cause runtime "multiple providers" warnings or missing methods.

## 5. File 2 — `src/main/resources/logback.xml`

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%msg requestId=%X{requestId:-none} tenantRef=%X{tenantRef:-none}%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

**What each part means:**

- `%msg`: the logger event message. The exercise uses `event=request_received` and other event names as messages.
- `%X{requestId}` / `%X{tenantRef}`: reads the corresponding value from the event's MDC.
- `:-none`: if the key is absent, prints `none`. This is a **display default**, not a value added into MDC automatically.
- `%n`: platform-appropriate newline.
- `<root level="INFO">`: accepts INFO logs and above. The example omits timestamp/level/thread to keep the learning output deterministic; production configurations should include timestamp, severity, service, and an appropriate structured format.

**Do not add multiple appenders just to see MDC.** If both root and a child logger attach the same console appender while additivity is enabled, a single log event may be printed twice, which is easily mistaken for an MDC bug. For the goals of this exercise, a single root appender is enough.

This pattern is **key=value text**, not JSON; if a client-controlled field contains whitespace or newlines, the data can break parsers. That is why the demo code only accepts IDs made of letters, digits, `_`, and `-`. In production, use a structured encoder with escaping/redaction rather than relying on a text pattern as the sole security measure.

## 6. File 3 — `MdcProject.java`: Creating Scopes, Propagating to Workers, Cleaning Up Context

Save at `src/main/java/demo/logging/mdc/MdcProject.java`:

~~~java
package demo.logging.mdc;

import java.util.Map;
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class MdcProject {
    private static final Logger LOG =
            LoggerFactory.getLogger(MdcProject.class);

    // Accept only demo IDs that are safe for text logs.
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private MdcProject() {
    }

    private static void validateId(String name, String value) {
        if (value == null || !SAFE_ID.matcher(value).matches()) {
            throw new IllegalArgumentException("Invalid " + name);
        }
    }

    // Restore the original map before the scope, even when there are no keys.
    static void restore(Map<String, String> context) {
        if (context == null || context.isEmpty()) {
            MDC.clear();
        } else {
            MDC.setContextMap(context);
        }
    }

    // A request boundary that holds fields for the scope of task.call().
    static <T> T withRequest(
            String requestId, String tenantRef, Callable<T> task)
            throws Exception {

        validateId("requestId", requestId);
        validateId("tenantRef", tenantRef);
        Objects.requireNonNull(task, "task");

        Map<String, String> before = MDC.getCopyOfContextMap();
        try {
            // The demo completely isolates requests A and B.
            MDC.clear();
            MDC.put("requestId", requestId);
            MDC.put("tenantRef", tenantRef);
            return task.call();
        } finally {
            // Executes even if the task fails or is cancelled.
            restore(before);
        }
    }

    // Capture MDC on the SUBMITTING thread; set and restore it on the RUNNING thread.
    static Runnable captureMdc(Runnable task) {
        Objects.requireNonNull(task, "task");
        Map<String, String> snapshot =
                MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> before =
                    MDC.getCopyOfContextMap();
            try {
                restore(snapshot);
                task.run();
            } finally {
                restore(before);
            }
        };
    }

    private static void process(
            String requestId, String tenantRef,
            ExecutorService worker) throws Exception {

        withRequest(requestId, tenantRef, () -> {
            LOG.info("event=request_received");

            Future<?> future = worker.submit(captureMdc(
                    () -> LOG.info("event=background_processed")));
            future.get();

            LOG.info("event=request_finished");
            return null;
        });
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker =
                Executors.newSingleThreadExecutor();

        try {
            process("req-A", "tenant-1", worker);
            process("req-B", "tenant-2", worker);

            // Non-request task: must not receive any prior context.
            worker.submit(captureMdc(
                    () -> LOG.info("event=periodic_cleanup"))).get();
        } finally {
            worker.shutdown();
            if (!worker.awaitTermination(5, TimeUnit.SECONDS)) {
                worker.shutdownNow();
            }
        }
    }
}
~~~

### Important Notes on Java and MDC

1. `MDC.getCopyOfContextMap()` returns a **copy** of the current map, or `null` when there is no context. Never pass a shared mutable map across requests and let threads mutate it.
2. `withRequest(...)` captures `before` and then initializes the request scope. The `finally` block restores the caller context even if `task.call()` throws an exception.
3. The demo calls **`MDC.clear()` on request entry** to make it easy to observe that no values leak. **In applications with tracing instrumentation**, clearing the entire map can wipe out `traceId`/`spanId` set earlier. In that case, middleware needs a coordinated strategy: only replace keys it owns, or inherit the verified trace context properly and restore the snapshot after the scope. Do not blindly copy the demo's `clear()` into every framework without understanding its filter chain.
4. `captureMdc(...)` **takes a snapshot when the wrapper is called** (on the producer thread). On the worker, it applies the snapshot, runs the task, and finally restores the previous context. Calling `MDC.put(...)` on an HTTP thread alone **does not** transfer values to an `ExecutorService`.
5. `newSingleThreadExecutor` intentionally uses a single reused worker to test the case where requests A and B run sequentially on the **same thread** — where context leakage is hardest to spot.
6. `Future.get()` forces each task to finish before logging `request_finished`, making the output order deterministic. In multi-threaded production environments, do not assume events from independent requests have a strict total order.
7. `SAFE_ID` only validates format to reduce newline/log injection. It **does not verify tenant permissions**. In a real API, `tenantRef` must come from an authenticated principal/authorization context or a trusted envelope after verification, not by trusting a raw client-sent `X-Tenant-Id` header.
8. `requestId` is a correlation ID, not an authorization token, not an error code, and not a replacement for a trace ID. Untrusted incoming IDs must have a boundary that generates or validates IDs according to a contract.
9. In this demo, `withRequest(...)` and `captureMdc(...)` are package-private so JUnit tests in the same package can call them; in larger applications, they can be packaged into a dedicated helper or `TaskDecorator`.
10. This wrapper fits the `Runnable`/`ExecutorService` example. For `Callable<V>`, `CompletionStage`, Reactor, virtual threads, or framework-managed executors, use the appropriate propagation adapter and framework context rather than treating this code as a generic library for all environments.

### Why Not Just Call `MDC.clear()` After the Task?

Simply calling `MDC.clear()` wipes out any pre-existing context on the worker or caller. With one scope nested inside another, that loses valid keys belonging to the outer call. Capturing `before` and calling `restore(before)` preserves nested scopes. However, if a worker **already has leaked MDC from other buggy code**, restoring `before` does not cure the pre-existing leak: entry points of independent requests/tasks must be kept clean and tested from the start.

## 7. Running the Project and Checking Output

From the `mdc-practice` directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.logging.mdc.MdcProject
~~~

**Seven expected log lines from the given code and pattern:**

~~~text
event=request_received requestId=req-A tenantRef=tenant-1
event=background_processed requestId=req-A tenantRef=tenant-1
event=request_finished requestId=req-A tenantRef=tenant-1
event=request_received requestId=req-B tenantRef=tenant-2
event=background_processed requestId=req-B tenantRef=tenant-2
event=request_finished requestId=req-B tenantRef=tenant-2
event=periodic_cleanup requestId=none tenantRef=none
~~~

These lines represent the **expected logger output** with the provided `logback.xml`, excluding Maven/JVM diagnostic messages if a tool emits diagnostics or another logging configuration is loaded. The equivalent flow for scope/copy/restore and event ordering was checked with Java `ThreadLocal` via JShell; the SLF4J/Logback example should be run with the Maven dependencies in your own environment for actual verification.

Points to observe:

- The `request_received`/`request_finished` pair for each request shares the same `requestId` and `tenantRef`.
- `background_processed` runs on the worker yet preserves the exact snapshot captured at submit time.
- Request B **does not carry** `req-A` or `tenant-1` even though the worker is reused.
- `periodic_cleanup` is outside any request, so it uses the default `none`. It **has no fabricated requestId**.
- There is no need to pass IDs into every `LOG.info(...)` call; the layout reads MDC for the scope.

If logs show only the message without `requestId`, check that `src/main/resources/logback.xml` is on the runtime classpath, check the provider version, the `%X` pattern, and the `MDC.put` calls. If the worker prints `none` for both A and B, the wrapper was not called **before submitting**, or the context was cleared too early.

## 8. File 4 — JUnit Unit Tests for Propagation and Cleanup

Save at `src/test/java/demo/logging/mdc/MdcProjectTest.java`:

~~~java
package demo.logging.mdc;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.slf4j.MDC;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class MdcProjectTest {
    @Test
    void scopeRestoresCallerEvenWhenTaskThrows() {
        MDC.clear();
        MDC.put("requestId", "caller");

        try {
            assertThrows(IllegalStateException.class, () ->
                    MdcProject.withRequest(
                            "req-X", "tenant-X", () -> {
                                assertEquals(
                                        "req-X", MDC.get("requestId"));
                                assertEquals(
                                        "tenant-X", MDC.get("tenantRef"));
                                throw new IllegalStateException(
                                        "expected");
                            }));

            assertEquals("caller", MDC.get("requestId"));
            assertNull(MDC.get("tenantRef"));
        } finally {
            MDC.clear();
        }
    }

    @Test
    void copiedContextReachesWorkerButDoesNotLeak() throws Exception {
        ExecutorService worker =
                Executors.newSingleThreadExecutor();
        MDC.clear();

        try {
            MDC.put("requestId", "req-A");
            MDC.put("tenantRef", "tenant-1");

            AtomicReference<String> seen =
                    new AtomicReference<>();
            worker.submit(MdcProject.captureMdc(() ->
                    seen.set(MDC.get("requestId")
                            + "/" + MDC.get("tenantRef")))).get();

            assertEquals("req-A/tenant-1", seen.get());

            // Next task on the same worker, without the wrapper:
            // Task A's MDC has been restored to an empty state.
            assertNull(worker.submit(
                    () -> MDC.get("requestId")).get());

            // The caller thread still retains A's context.
            assertEquals("req-A", MDC.get("requestId"));
        } finally {
            MDC.clear();
            worker.shutdown();
            if (!worker.awaitTermination(5, TimeUnit.SECONDS)) {
                worker.shutdownNow();
            }
        }
    }

    @Test
    void rejectsUnsafeIdsBeforeLogging() {
        MDC.clear();
        assertThrows(IllegalArgumentException.class, () ->
                MdcProject.withRequest(
                        "req-bad\ninjection", "tenant-1",
                        () -> null));
        assertNull(MDC.get("requestId"));
    }
}
~~~

Run:

~~~bash
mvn test
~~~

Surefire output depends on Maven and the environment, but **the expected result is 3 tests, 0 failures, 0 errors**. Test reports can be viewed in `target/surefire-reports/`. Avoid snapshotting the entire console output as an assertion, because timestamps or thread names can vary if the pattern changes.

**Why are these three tests necessary?**

1. **Exception path**: `finally` restores the caller's MDC even when the work throws.
2. **Executor path**: request A's snapshot reaches the worker; once the task completes, the worker does not retain request A's `requestId`, and the caller remains unchanged.
3. **Input validation**: strings with newlines are rejected before entering MDC/logs, preventing forged log lines.

These tests are a baseline and do not replace integration tests with a real HTTP filter, message consumer, or tracing agent. For reactive systems, propagation must be tested separately across schedulers and callbacks.

### Verifying Failure Modes by Intentionally Breaking the Code

In a **dev/test** environment, try removing the wrapper at the call site:

~~~java
// Only for observing the bug in this exercise; do not use in the final version.
Future<?> future = worker.submit(
        () -> LOG.info("event=background_processed"));
~~~

The worker may print `requestId=none tenantRef=none` even though the request thread has context. With Logback, an executor, and this scoping setup, MDC does not automatically propagate to the worker. Once you observe this, **restore `captureMdc(...)`** and re-run all three tests.

Try removing `finally` in `withRequest`: the caller still holds `requestId=req-A` after processing, and non-request tasks may pick up the wrong context. This demonstrates why restoration is required even on the exception path.

**Never introduce this bug in a production system just to test it.**

## 9. Integrating MDC into a Real HTTP Application

In a servlet application, the natural place to set up MDC is a **Filter/middleware**:

~~~text
HTTP request arrives
   |
   v
Authenticate / verify tenant
   |
   v
Read-or-generate trusted requestId
   |
   v
Capture previous MDC; put requestId/tenantRef
   |
   v
Controller -> Service -> Repository logs
   |
   v
finally: restore original MDC
   |
   v
HTTP response
~~~

Pseudo-Java snippet (not a standalone compilable servlet class):

~~~java
Map<String, String> before = MDC.getCopyOfContextMap();
try {
    MDC.put("requestId", verifiedOrGeneratedRequestId);
    MDC.put("tenantRef", trustedTenantRef);
    filterChain.doFilter(request, response);
} finally {
    if (before == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(before);
    }
}
~~~

**This snippet differs from the demo `withRequest` in that it preserves pre-existing keys** (such as trace context set by an agent). Only apply this when the boundary/framework already clears per-request context and has no stale keys; if you need to reset middleware-owned keys, save/restore those specific keys or build a framework-specific scope adapter. `verifiedOrGeneratedRequestId` must be validated for length, character set, namespace, and trust. `trustedTenantRef` must come from the authorization context, never using a raw client header as proof of access.

Implementation notes:

- Place the middleware so that controller/service logs see MDC while the context is cleaned up after the request completes.
- A filter running before authentication cannot assert a trusted `tenantRef`; it can be added after the principal is authenticated.
- If a servlet starts an `async request`, subsequent processing may happen on a different thread; proper propagation and async lifecycle callbacks are required rather than assuming the filter's `finally` covers all async work.
- A request without a user/tenant (such as a health check) may omit `tenantRef` or use a defined value rather than guessing a tenant.
- `traceId`/`spanId` must come from instrumentation; **do not** generate a fake string named `traceId` that misleads dashboards into thinking real tracing exists.

## 10. Integrating MDC in Message Consumers and Jobs

For Kafka/RabbitMQ/JMS consumers, MDC is typically set when **starting to process a message** and cleaned up when the callback finishes. Example flow:

~~~text
receive message
   |
   +-- validate envelope/messageId, tenant permission, correlation context
   |
   +-- MDC.put("messageId", ...)
   +-- MDC.put("tenantRef", ...)
   |
   +-- process + retry/fallback/logging
   |
   +-- finally restore/clear MDC
   |
   +-- ACK/NACK/commit per broker contract
~~~

No MDC mechanism automatically transmits `messageId`/`traceId` across a broker. The producer must place correlation metadata into **message headers/envelope**, and the consumer must read and validate it before setting the local scope.

Notes:

- An application `messageId` may remain the same across redeliveries; `deliveryAttempt` is a separate field.
- Do not use a broker offset, RabbitMQ `deliveryTag`, or MDC `tenantRef` as a default idempotency key.
- If code catches exceptions to retry, the MDC scope must be closed after each attempt; do not let attempt B see information from message A.
- If the caller submits tasks to an executor or `CompletableFuture`, use an appropriate wrapper, `TaskDecorator`, or context propagation; do not rely on thread names to correlate messages.
- Scheduler logs must not attach a fake `requestId` if the job does not belong to a request. Use a defined `jobId` or `runId`.

MDC is **observability metadata**; it does not provide ACK, retry, transaction, durability, or exactly-once guarantees.

## 11. MDC, ThreadLocal, Virtual Threads, and Async Appenders

Logback's MDC is **thread**-scoped. This leads to several limitations:

- **Thread pools:** tasks run on reused threads; you must capture and restore to avoid stale data.
- **`CompletableFuture`:** callbacks may run on another thread or immediately on the completing thread; propagate at the appropriate boundary rather than arbitrarily reading the caller's MDC at callback time.
- **Reactor/async frameworks:** work can hop across schedulers continuously; use the framework's built-in integration/context propagation rather than calling `MDC.put` in one place and assuming it follows the reactive chain.
- **Virtual threads:** MDC remains bound to the currently executing thread, but there are many short-lived virtual threads; correlation across tasks does not happen automatically. Measure `ThreadLocal` impact and follow framework tracing context conventions.
- **Async appenders:** events may be formatted on a different thread after the request scope has closed. The backend must capture MDC inside the **log event** at emission time; do not read `MDC.get("requestId")` on the writer thread and attribute it to the source event. Logback supports MDC on log events, but you should verify the entire pipeline when custom layouts or bridges are involved.

If you need to propagate `Runnable`/`Callable<T>` without writing wrappers everywhere, you can use a framework's `TaskDecorator` or instrumentation; you still need to test A → B → no-context task on the same thread pool.

### Is `MDC.putCloseable` Enough for Nested Scopes?

SLF4J provides `MDC.putCloseable(key, value)` for use with try-with-resources:

~~~java
// SLF4J snippet: suitable when managing only a single key.
try (MDC.MDCCloseable ignored =
             MDC.putCloseable("requestId", "req-A")) {
    LOG.info("event=started");
}
~~~

On `close()`, this helper **removes that key**. It does not promise to restore the **previous value of the same key** in a nested scope. If the caller already had `requestId=outer` and an inner block used `putCloseable` with `req-A`, closing it can **lose the key** instead of restoring `outer`. This exercise uses full-map snapshot/restore to avoid that bug.

Additionally, `MDC.putCloseable` only manages the current thread and **does not automatically propagate** when submitting tasks to an executor.

## 12. Adding MDC to Structured Logging and OpenTelemetry

Do not confuse MDC with a JSON encoder or trace context:

- **MDC** provides a key–value map within a thread scope.
- **`PatternLayout` `%X`** turns values into part of text output.
- **Structured logging encoders** can output MDC entries as JSON fields for accurate filtering and indexing.
- **OpenTelemetry logs** have `Resource`, `Attributes`, and dedicated `TraceId`/`SpanId`. A bridge, appender, or collector may map MDC into attributes, but exact behavior depends on instrumentation, backend, and configuration.
- **Distributed tracing** requires real trace context extracted/injected over HTTP/messages with an appropriate propagator. Calling `MDC.put("traceId", randomValue)` manually does not create a span and can break trace lookup.

For example, with SLF4J 2.x, log-event-specific fields should use fluent key–value pairs:

~~~java
// Snippet; requires SLF4J 2.x and a supporting backend/encoder.
LOG.atInfo()
   .addKeyValue("event", "order_processed")
   .addKeyValue("durationMs", 28)
   .addKeyValue("outcome", "success")
   .log("Order processing completed");
~~~

If MDC already holds `requestId`/`tenantRef`, scope-level fields and event-specific fields can be combined **when the encoder is configured to support it**. The pattern from section 5 does not print `addKeyValue` fields automatically: if you want typed JSON fields, choose an encoder/layout that supports them and test the actual output.

### What Should Not Be Put into MDC?

| Field | Assessment |
| --- | --- |
| Opaque, validated `requestId` | Usually appropriate |
| `correlationId` for workflows | Appropriate if the contract is clear |
| `tenantRef` from authenticated principal | Can be appropriate, but requires access-control policies |
| `traceId` from active tracing context | Usable when integration is properly configured |
| Per-event `durationMs`, `outcome` | Usually better as event fields |
| Passwords, OTPs, JWTs, cookies, API keys | **Do not put into MDC/logs** |
| Full URL query strings, bodies, headers | Do not log verbatim; high risk of data exposure |
| Emails, phone numbers, persistent user identifiers | Only when strictly needed and permitted; consider pseudonymization |
| Raw `toString()` of requests/entities | No; easily becomes huge and leaks PII |

MDC **is not a session store** or an authorization context. Seeing `tenantRef=tenant-1` in a log does not authorize a viewer to access that tenant's logs; the backend must enforce RBAC and tenant isolation independently.

## 13. Cost and Performance

Every MDC key printed on every log line increases log volume. At 100,000 log events/day, adding a few hundred bytes per event can add tens of MB/day before indexing and replication. Only add fields with genuine investigative value.

- Set MDC at the **boundary**, rather than calling `MDC.put(...)` around every log statement.
- Do not stuff exception stack traces or large objects into the map.
- Use consistent field names and an owned schema.
- Do not use `requestId`/`userId`/`messageId` as **metric labels** in Prometheus: cardinality approaches the number of requests/entities, making time series prohibitively expensive.
- Measure overhead when propagating context across thousands of tasks/second; snapshotting maps and creating wrappers both carry cost. Having dozens of fields in MDC is also a sign of over-enrichment.
- Backends with async queues may drop or block under policy; correct MDC does not guarantee an event was durably written.
- If application logs and traces are ingested via two pipelines, avoid unintentional duplicate ingestion.

MDC helps search by request, but log quality still depends on error codes, event names, timestamps, storage retention, and log accessibility. Adding `requestId` will not fix a log message that fails to describe what happened.

## 14. Common Issues and Troubleshooting

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Logs have only the message, no ID | `logback.xml` not loaded or pattern missing `%X` | Check runtime classpath, backend, and pattern |
| `requestId=none` in controller | MDC not set before logging, or cleared too early | Set at the proper request boundary |
| `requestId=none` in worker | Not captured/restored across executor | Use `captureMdc(...)` / `TaskDecorator` |
| Request B carries A's ID | MDC not cleaned up on thread pool | `finally` restore/clear; test A→B→no-context |
| Caller ID lost after nested scope | `MDC.clear()` or `putCloseable` wiped prior key | Snapshot and restore map/key before scope |
| `traceId` set, but trace won't open | Self-generated ID with no active span/exporter | Obtain context from the tracing SDK |
| No MDC values when using SLF4J | Backend lacks support or API/provider version mismatch | Inspect dependency tree; pick a single backend |
| Multiple console lines for one event | Logger hierarchy/additivity or duplicate appenders | Fix routing; do not blame MDC |
| Wrong or spoofed `tenantRef` | Trusting raw request header | Derive tenant from authenticated principal |
| Logs contain forged newlines | Missing input validation | Bound length and handle escaping/control characters |
| Logger has IDs, JSON backend drops them | Encoder/collector does not map MDC | Integration-test structured output |
| MDC `errorCode` lingers after recovery | Event-specific data placed in an overly long scope | Use event key–value or a shorter scope |
| Metric queries too heavy | `requestId` used as a metric label | Keep IDs in logs/traces; use bounded labels |
| Tests pass, production leaks MDC | Framework async/callback differs from demo | Test with real executor/filter/consumer |
| Logs contain email/token from MDC | Sensitive data added without minimization | Whitelist metadata; redact at source |

**How to inspect dependencies** when the program does not behave as expected:

~~~bash
mvn dependency:tree
~~~

Look for `org.slf4j:slf4j-api` and **one** expected SLF4J backend/provider (for example `logback-classic`). In a Spring Boot application, the starter may bring the provider; do not add `slf4j-simple` alongside Logback as a "quick fix," because multiple providers can trigger warnings or unpredictable backend selection.

## 15. Exercise Acceptance Criteria

An "Adding MDC" implementation is considered complete when:

1. The project compiles with Java 17 and uses **real SLF4J MDC** with Logback.
2. `logback.xml` includes `%X{requestId:-none}` and `%X{tenantRef:-none}`.
3. Request A outputs `req-A/tenant-1` on both request logs and worker logs.
4. Request B outputs `req-B/tenant-2`, with **no** context from A.
5. Non-request jobs print `requestId=none tenantRef=none`.
6. Scopes use `try/finally` and restore the caller context when an exception is thrown.
7. Workers capture MDC **before submission** and clean up after execution.
8. `mvn test` passes **all three tests**, covering exception cleanup, propagation, and ID validation.
9. Unverified client tenant headers are not used for authorization or log routing.
10. Secrets/excessive PII are not logged; a typed structured output strategy is in place if using a collector.
11. Tested against the actual logging provider/version, not only internal unit mocks.
12. Clear documentation notes that MDC **does not automatically cross HTTP/message brokers** and does not create distributed traces on its own.

### Verifiable Extension Exercises

**A. Add `correlationId`:** set a valid ID alongside the request, update the pattern to display it, and add a test verifying it reaches the worker and does not leak to the next request. Do not generate a new ID for every log event.

**B. Add `traceId` properly:** integrate OpenTelemetry Java instrumentation, obtain trace/span IDs from the **active context**, and output them via a supported bridge/encoder; verify that the trace link opens when spans are exported. Do not use fake strings to simulate tracing.

**C. Handle worker failures:** have the worker throw an exception; use `Future.get()` on the caller to observe the failure, preserve `finally` cleanup, and log the stack trace only once at the boundary that decides the outcome. Do not log and rethrow at every layer.

**D. Integrate a Spring/Servlet filter:** apply MDC at a real request boundary, setting `requestId` from a validated header or server-generated value and `tenantRef` from authentication. Test two requests on the same thread pool and an exception path; avoid wiping context owned by other tracing instrumentation.

**E. JSON encoder:** replace the text pattern with a backend-compatible JSON encoder and emit MDC entries as fields. Write an integration test asserting that `requestId`/`tenantRef` are string fields, contain no forged newlines, and do not log tokens.

## 16. Production Readiness Checklist

- [ ] Define the scope and ownership of MDC keys: `requestId`, `tenantRef`, `correlationId`, `traceId`.
- [ ] Generate/validate IDs at the boundary; derive tenant from authenticated identity.
- [ ] Set MDC once at the start of the scope and **restore in `finally`** on every exit path.
- [ ] Coordinate with tracing instrumentation so keys/contexts owned by other components are not wiped.
- [ ] Snapshot MDC before submitting tasks to thread pools; use appropriate adapters for async/reactive/broker flows.
- [ ] Use an appropriate Logback pattern or structured encoder and test **real** output.
- [ ] Do not log secrets, unnecessary PII, or raw headers/payloads.
- [ ] Enforce length/character-set bounds and prevent log injection.
- [ ] Do not put `requestId`/`userId` into metric labels or global `Resource` fields.
- [ ] Test request A→B→no-context, nested scopes, exception paths, cancellation, and retries.
- [ ] Verify logging backend/provider, duplicate appenders, latency/drop behavior, and log retention.
- [ ] Document keys, schemas, log access permissions, and dependency update policies.

**Conclusion:** Adding MDC properly is more than calling `MDC.put(...)`. You need to **establish trusted ID sources**, **choose useful keys**, **protect per-request lifecycles**, **propagate context across async boundaries**, **configure the backend to actually output MDC**, and **test for zero leakage between tasks**. The Java 17 project above provides a complete cycle for observing and verifying all of those requirements.

### References

- Logback — [Mapped Diagnostic Context](https://logback.qos.ch/manual/mdc.html): MDC usage, thread scoping, `finally` cleanup recommendations, and executor snapshots.
- Logback — [Layouts and `%X{key:-default}` syntax](https://logback.qos.ch/manual/layouts.html); [Logback 1.6 release notes](https://github.com/qos-ch/logback/releases).
- SLF4J — [Manual](https://www.slf4j.org/manual.html), [MDC API/Javadocs](https://www.slf4j.org/apidocs/org/slf4j/MDC.html), [Download/versions](https://www.slf4j.org/download.html).
- Maven — [Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/), [Surefire](https://maven.apache.org/surefire/maven-surefire-plugin/), [Exec Maven Plugin](https://www.mojohaus.org/exec-maven-plugin/).
- JUnit — [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/).
- OpenTelemetry — [Context propagation](https://opentelemetry.io/docs/concepts/context-propagation/), [Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/).
- OWASP — [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
