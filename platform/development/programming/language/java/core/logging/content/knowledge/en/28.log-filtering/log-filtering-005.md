# Context-Based Filtering in Java Core Logging

## 1. What is context-based log filtering?

**Context-based filtering** is the decision to **keep, drop, or route** a log event based on contextual attributes attached to the execution, rather than relying solely on the log level (`INFO`, `DEBUG`, `ERROR`), logger name, or message text.

For example, in a multi-tenant service:

- `tenantId=tenant-a`: a record can be routed additionally to a dedicated file/index for tenant A.
- `tenantId=tenant-b`: the record must not be included in tenant A's dedicated output.
- `requestId=req-42`: records related to request 42 can be selected for investigation.
- `jobType=batch` or `component=payment`: determines the detail level, collection route, or alerting by context.
- `traceId=...` and `spanId=...`: correlate events within the same trace; having a trace ID does not by itself grant access to log data.

**Key point:** the context must be present **when the log event is created and passes through the filtering point**. If the event is processed asynchronously or handed off to another thread, you must clearly understand where the context is captured and propagated. Filtering incorrectly can cause two serious failures: one tenant's logs leaking into another tenant's output, or critical error logs being lost completely.

Do not confuse these four operations:

| Operation | Typical Criterion | Result |
| --- | --- | --- |
| Selecting by **logger level** | `com.example=INFO` | Drops DEBUG/TRACE below the threshold; does not distinguish request/tenant |
| **Context-based filtering** | `tenantId=tenant-a` | Includes/excludes events based on metadata belonging to the request, job, or tenant |
| **Formatting / enrichment** | `%X{requestId}` | Displays/adds context fields; **does not mean filtering occurred** |
| **Post-collection search/query** | `tenantId:"tenant-a"` in the log backend | Queries events that were already collected; cannot recover logs dropped by a filter |

You must distinguish between **filtering to reduce noise**, **context-based routing**, and **log access control**. Application-level filtering is only one part of the pipeline. If tenant data isolation is required, access control must be enforced at the destination/storage layer, and a client-supplied tenant ID must never be trusted directly.

## 2. Where does context come from and what should it contain?

In Java using SLF4J/Logback, contextual data typically lives in the **MDC (Mapped Diagnostic Context)**: a `String → String` map bound to the current thread. Log4j 2 provides an equivalent mechanism called the **Thread Context Map** (`ThreadContext`). Fields from tracing or frameworks can be added via dedicated integrations.

Example events (illustrative):

~~~text
2026-11-10T09:41:00.120Z INFO  tenantId=tenant-a requestId=req-42 event=invoice_created
2026-11-10T09:41:00.121Z ERROR tenantId=tenant-b requestId=req-43 event=payment_failed
2026-11-10T09:41:00.125Z INFO  tenantId=tenant-a requestId=req-44 event=invoice_sent
~~~

The filter `tenantId == tenant-a` selects the two lines for A. `requestId` is used to correlate by request; **it does not replace tenantId** when destination rules require tenant partitioning. Filtering by checking the log message with `contains("tenant-a")` is unreliable: that substring may appear in text by coincidence, break when formatting changes, or be injected by user input.

Choose keys with stable semantics: `tenantId`, `requestId`, `traceId`, `jobId`, `operation`. Values must come from context that has been authenticated/validated at the system boundary. Do not put passwords, tokens, cookies, access credentials, sensitive personal data, or large payloads into context. Sanitize control characters and bound the length of fields originating externally.

MDC is neither a durable business data store nor a security mechanism. It helps produce diagnostic records; filtering and routing must still comply with the application's information security policy.

## 3. Where do filters sit in the pipeline?

A common path:

~~~text
logger.info(...)
    |
    v
[logger level / early filter] -> [create LogEvent + capture context]
    |
    +--> [CONSOLE appender] --> shared log
    |
    +--> [tenantId filter] --> [TENANT_A appender] --> selective log
    |
    +--> [async queue] --> [log writer worker] --> storage destination
~~~

The exact order depends on the backend and where the filter is attached. Filtering before event creation can reduce the cost of creating/logging events. Filtering at the appender allows the same event to be **kept in the shared console** while **excluded from a dedicated file**.

Frameworks such as Logback and Log4j 2 use tri-state filter results:

| Result | Practical Meaning |
| --- | --- |
| `DENY` | Drops the event at that filtering point |
| `NEUTRAL` | Makes no final decision; continues to the next rule/filter or default handling |
| `ACCEPT` | Accepts at the current filtering stage, potentially bypassing remaining filters in the same stage |

**Do not equate `ACCEPT` with "written to every appender" or "bypasses every logger level"**: the exact effect depends on the stage and backend. For example, a Logback turbo filter and a Log4j 2 global filter can decide very early; an appender filter only controls that specific appender. Therefore, when letting events pass to a dedicated sink, `onMatch=NEUTRAL` and `onMismatch=DENY` are usually more predictable than forcing `ACCEPT` across multiple filter layers.

A rule should explicitly handle all three cases: **match**, **mismatch**, and **missing/null context**. For a sink dedicated to tenant A, a missing `tenantId` should be treated as **not eligible for that sink**; however, you should not silently drop all ERRORs from every sink.

## 4. Standalone Java 17 example: filtering by attributes attached directly to LogRecord

`java.util.logging` (JUL) provides the `java.util.logging.Filter` interface, but **does not provide a standard MDC like SLF4J/Logback**. We can pass an explicit context snapshot via `LogRecord` and let the handler read the event that already carries its context. The goal of this example is to illustrate the core principle: filter decisions are based on **metadata attached to the event**, not on message substrings or a ThreadLocal at writer execution time.

Save as **`ContextFilterDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.logging.Filter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ContextFilterDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.context");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        CollectingHandler tenantSink = new CollectingHandler();
        tenantSink.setLevel(Level.ALL);
        tenantSink.setFilter(new TenantFilter("tenant-a"));
        logger.addHandler(tenantSink);

        try {
            emit(logger, "tenant-a", "event=created");
            emit(logger, "tenant-b", "event=ignored");
            emit(logger, "tenant-a", "event=updated");

            for (String line : tenantSink.lines) {
                System.out.println(line);
            }
            System.out.println("count=" + tenantSink.lines.size());
        } finally {
            logger.removeHandler(tenantSink);
            tenantSink.close();
        }
    }

    private static void emit(Logger logger, String tenantId, String message) {
        LogRecord event = new LogRecord(Level.INFO, message);
        event.setLoggerName(logger.getName());

        // Fixed snapshot attached to the event; do not read ThreadLocal later.
        event.setParameters(new Object[] { Map.of("tenantId", tenantId) });
        logger.log(event);
    }

    private static final class TenantFilter implements Filter {
        private final String allowedTenant;

        private TenantFilter(String allowedTenant) {
            this.allowedTenant = allowedTenant;
        }

        @Override
        public boolean isLoggable(LogRecord event) {
            Object[] parameters = event.getParameters();
            if (parameters == null || parameters.length == 0 ||
                    !(parameters[0] instanceof Map<?, ?> context)) {
                return false; // No context: reject in this dedicated sink.
            }
            return allowedTenant.equals(context.get("tenantId"));
        }
    }

    private static final class CollectingHandler extends Handler {
        private final List<String> lines = new ArrayList<>();

        @Override
        public void publish(LogRecord event) {
            if (!isLoggable(event)) {
                return;
            }
            Map<?, ?> context = (Map<?, ?>) event.getParameters()[0];
            lines.add("tenant=" + context.get("tenantId") +
                    " " + event.getMessage());
        }

        @Override
        public void flush() {
            // No I/O or separate buffer in this example.
        }

        @Override
        public void close() {
            // No external resources to close.
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 ContextFilterDemo.java
java ContextFilterDemo
~~~

**Expected exact stdout**:

~~~text
tenant=tenant-a event=created
tenant=tenant-a event=updated
count=2
~~~

Explanation:

1. Both the logger and the handler allow `INFO`; whether an event is included or excluded is decided by **`TenantFilter`**. If you raise the logger level threshold to block an event before the handler, the filter cannot recover that event.
2. `emit(...)` places each event's immutable map into `LogRecord.parameters`. This is an **example-specific convention**, not a standard JUL MDC protocol; other formatters will not automatically understand the `tenantId` key.
3. `Handler.isLoggable(...)` checks both the level and the filter attached to the handler. The handler only appends the message when it passes both.
4. Events for `tenant-b` do not reach tenant A's list; events without context are also rejected at this sink.
5. Because the program writes synchronously and emits events from a single thread, the order of collected lines is deterministic. When moving to async logging, you must preserve the context on each event before placing it onto the queue.

This example intentionally uses an in-memory sink so that stdout does not depend on timestamps, console formatters, or external backends. In a real application, configure it to **keep important error logs in a shared sink** alongside the filtered sink; never use a selective sink as the sole operational output.

## 5. SLF4J MDC: scoping context properly

With SLF4J and an MDC-capable backend, business code can set keys before emitting logs. The following snippet requires `org.slf4j:slf4j-api` and a compatible backend; **it is not a standalone JDK program**.

~~~java
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

final class InvoiceService {
    private static final Logger LOG =
            LoggerFactory.getLogger(InvoiceService.class);

    void process(String verifiedTenantId, String requestId) {
        // Also safe for nested calls that already have MDC from the caller.
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            MDC.put("tenantId", verifiedTenantId);
            MDC.put("requestId", requestId);

            LOG.info("event=invoice_started");
            LOG.debug("event=invoice_validation_complete");
            LOG.info("event=invoice_succeeded");
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    }
}
~~~

Note: `verifiedTenantId` must be determined from authenticated information accepted by the application; never use a self-declared HTTP header directly for log isolation rules. The example assumes `verifiedTenantId` and `requestId` are non-null per the caller contract. If required values are absent, choose an explicit policy (reject processing, omit the key, or route to a shared sink) rather than silently attaching an incorrect value.

- `MDC.put(...)` mutates the context on the **current thread**.
- `MDC.getCopyOfContextMap()` captures a copy of the previous state; the `finally` block restores it so nested code does not wipe out the caller's MDC.
- For independent requests on reused servlet/worker threads, you must clear the context after the request finishes, even when an exception is thrown.
- To render context fields, the backend must use an appropriate layout/encoder, such as Logback's `%X{tenantId}` and `%X{requestId}`. Printing these fields **does not automatically enable filtering**.
- `MDC.putCloseable("key", value)` helps clean up a single key via try-with-resources, but its `close` **removes the key**; when you need to preserve nested context, the snapshot/restore pattern above expresses the intent more clearly.

## 6. Logback: filtering by MDC at a dedicated appender

Logback Classic supports **appender filters** that receive an `ILoggingEvent`. For a sink dedicated to tenant A, we write a small filter that reads the **MDC attached to the event** via `event.getMDCPropertyMap()`. You do not read whatever MDC happens to be on the file-writing thread: an async appender may process the event on a different worker thread.

In an application with Logback Classic, create the class **`com.example.logging.TenantAppenderFilter`** (snippet depends on Logback):

~~~java
package com.example.logging;

import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.filter.Filter;
import ch.qos.logback.core.spi.FilterReply;

public final class TenantAppenderFilter extends Filter<ILoggingEvent> {
    private String tenantId;

    public void setTenantId(String tenantId) {
        this.tenantId = tenantId;
    }

    @Override
    public FilterReply decide(ILoggingEvent event) {
        if (tenantId == null || tenantId.isBlank()) {
            return FilterReply.DENY;
        }
        String actual = event.getMDCPropertyMap().get("tenantId");
        return tenantId.equals(actual)
                ? FilterReply.NEUTRAL
                : FilterReply.DENY;
    }
}
~~~

Configuration **`logback.xml`** (assumes the class above is on the classpath and a compatible Logback version is used):

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger{24} tenant=%X{tenantId} request=%X{requestId} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="TENANT_A" class="ch.qos.logback.core.FileAppender">
        <file>tenant-a.log</file>
        <append>true</append>
        <filter class="com.example.logging.TenantAppenderFilter">
            <tenantId>tenant-a</tenantId>
        </filter>
        <encoder>
            <pattern>%d{ISO8601} %-5level tenant=%X{tenantId} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="TENANT_A"/>
    </root>
</configuration>
~~~

Processing flow in this configuration:

- Events with `tenantId=tenant-a` at level `INFO` or higher: written to **both console and TENANT_A file**.
- Events with `tenantId=tenant-b` or missing the key: still written to **console**, and receive `DENY` at **TENANT_A**.
- `DEBUG` events: dropped by the root `INFO` level rule; the filter on TENANT_A cannot bring them back.
- If the `tenantId` field is missing, the filter rejects at the targeted sink (fail-closed at the dedicated sink). The shared console still receives valid logs for diagnosing context-setup bugs.

Do not create a new `TenantAppenderFilter` for every tenant in a system with thousands of tenants and spawn thousands of files/appenders: resource and operational overhead becomes prohibitive. When large-scale separation is needed, consider a structured logging pipeline with partitioning and access control in the collection system.

### Logback TurboFilter and global scope

Logback also has **turbo filters** that run earlier than appender filters. For example, dropping logs *explicitly tagged* as health checks from the entire Logback pipeline:

~~~xml
<configuration>
    <turboFilter class="ch.qos.logback.classic.turbo.MDCFilter">
        <MDCKey>logCategory</MDCKey>
        <Value>routine-health-check</Value>
        <OnMatch>DENY</OnMatch>
        <OnMismatch>NEUTRAL</OnMismatch>
    </turboFilter>

    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder><pattern>%d %-5level %msg%n</pattern></encoder>
    </appender>
    <root level="INFO"><appender-ref ref="CONSOLE"/></root>
</configuration>
~~~

This is a **global log-drop policy**: any event with `logCategory=routine-health-check` can be dropped, including ERROR events, if you apply the rule regardless of severity. Use it only when business intent genuinely permits it. If the goal is merely to reduce noise in a specific file or alerting sink, attach the filter to that sink instead. Avoid using `OnMatch=ACCEPT` when you want to preserve logger level behavior, because an early-stage filter can interact with level selection.

**Do not use Janino expression evaluators from older configurations without checking the version.** In newer Logback versions, some Janino-based evaluators have been removed; a typed filter like the class above expresses the logic clearly and is easier to test.

## 7. Log4j 2: ContextMapFilter at the appender

Log4j 2 provides `ThreadContext` for attaching metadata and `ContextMapFilter` for reading the context map on a log event. Depending on where the filter is placed, Log4j 2 can filter at the global, logger, appender reference, or appender stage.

Example **`log4j2.xml`** routing only tenant A's events to a dedicated file alongside the shared console:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5level tenant=%X{tenantId} - %msg%n"/>
        </Console>

        <File name="TENANT_A" fileName="tenant-a.log">
            <ContextMapFilter onMatch="NEUTRAL" onMismatch="DENY">
                <KeyValuePair key="tenantId" value="tenant-a"/>
            </ContextMapFilter>
            <PatternLayout pattern="%d{ISO8601} %-5level tenant=%X{tenantId} - %msg%n"/>
        </File>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
            <AppenderRef ref="TENANT_A"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Example code using the Log4j 2 API (not a standalone program):

~~~java
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.apache.logging.log4j.CloseableThreadContext;

final class PaymentProcessor {
    private static final Logger LOG =
            LogManager.getLogger(PaymentProcessor.class);

    void run(String verifiedTenantId) {
        try (CloseableThreadContext.Instance ignored =
                     CloseableThreadContext.put("tenantId", verifiedTenantId)) {
            LOG.info("event=payment_started");
            LOG.info("event=payment_completed");
        }
    }
}
~~~

In the filter configuration above, `onMatch=NEUTRAL` lets matching events proceed under normal rules, while `onMismatch=DENY` excludes events not belonging to A from the **File appender**. `KeyValuePair` inspects the event's metadata, not the `%msg` string. With multiple key/value pairs, `operator="AND"` requires all conditions under the filter's rules to match, whereas `OR` allows any match; understand how multi-valued keys behave before applying them. Do not assume `ContextMapFilter` directly filters a `MapMessage`: it inspects the **context map**, while `MapFilter` is for map data on the message itself.

Log4j 2 also provides `DynamicThresholdFilter` to select a **log level threshold based on a context key**. That serves a different purpose from tenant-only routing. For instance, you can temporarily enable higher detail for a group of requests under investigation, provided you control time bounds and log volume. Filters running at different stages interact with logger levels; always verify the actual behavior with your deployed backend configuration.

## 8. Thread pools, async logging, and context leakage

**Having MDC on a request does not mean tasks submitted to an `ExecutorService` automatically carry that MDC to worker threads.** Thread pools reuse threads, leading to two common bugs:

1. **Missing context:** request A has `tenantId=A`, but the worker has no MDC set. The appender filter does not see A and drops the event from sink A.
2. **Stale/leaked context:** a worker running task A sets MDC and fails to clean it up; later, task B reuses that thread and accidentally emits `tenantId=A`. This bug is especially dangerous for tenant-based log routing.

Always capture context **on the submitting thread** and restore/clean it up on **every task execution**. The pattern below uses SLF4J MDC and is suitable for the boundary of **independent tasks**:

~~~java
import java.util.Map;
import org.slf4j.MDC;

final class MdcTaskWrapper {
    static Runnable wrap(Runnable task) {
        Map<String, String> captured = MDC.getCopyOfContextMap();
        return () -> {
            try {
                MDC.clear();
                if (captured != null) {
                    MDC.setContextMap(captured);
                }
                task.run();
            } finally {
                MDC.clear();
            }
        };
    }
}
~~~

Call `MdcTaskWrapper.wrap(...)` **right at the submission site**, while the calling thread still holds the tenant/request context:

~~~java
executor.execute(MdcTaskWrapper.wrap(() ->
        logger.info("event=async_work_started")));
~~~

This snippet requires `executor`/`logger` variables to be declared in the application. If you use `CompletableFuture`, scheduled executors, Reactor, or messaging systems, each async boundary may require its own propagation mechanism. **Never call `MDC.get(...)` on an async writer thread and assume it is the event's tenant**; use the context snapshot stored on the event, such as `ILoggingEvent.getMDCPropertyMap()` or Log4j 2's context data.

The `finally MDC.clear()` pattern fits independent tasks on a pool whose policy is that each task starts with a clean context. If the wrapper can run **nested** on the same thread with an already valid context, capture and restore the previous map at the boundary instead of unconditionally clearing it; lifecycle handling must be consistent across layers.

## 9. Policies for missing context, errors, and multiple sinks

A good design documents a clear decision table. For example, a system keeping a shared console and a dedicated file for tenant A:

| Event | Shared Console | TENANT_A File | Reason |
| --- | --- | --- | --- |
| `tenantId=A`, INFO | Keep | Keep | Matches the selected tenant |
| `tenantId=B`, INFO | Keep | Drop | Does not belong to tenant A |
| Missing `tenantId`, WARN | Keep | Drop | Tenant unknown; still needed for diagnostics |
| `tenantId=A`, DEBUG; root=INFO | Drop | Drop | Blocked by logger level before the appender filter |
| `tenantId=B`, ERROR | Keep | Drop | B's error must not leak into A's dedicated file |

If an event carries a forged `tenantId` sent by a client, tenant-filtered files can be misrouted. **Context filtering is not an access-control boundary**. Only set the tenant ID after authentication and authorization checks; the centralized logging system must still enforce appropriate query and retention permissions.

**Fail-closed** (if tenant is missing, do not write to the tenant sink) is appropriate for tenant-specific outputs; **failing open to a shared sink** to preserve operational logs is a separate decision. For audit/financial/security events, never arbitrarily drop events due to missing metadata; maintain a durable channel and an alert when context is invalid.

Pay attention to these cases:

- **Exceptions:** log throwables at an appropriate handling level; a filter can still drop an exception if attached globally and context is missing.
- **Switching tenants within a request:** do not mutate MDC ad hoc and forget to revert; scoped boundaries and authenticated IDs help prevent mixed logs.
- **Runtime configuration reloads:** avoid applying overly broad rule changes without testing and rollback; raising log volume can create heavy load.
- **Multiple appenders:** define which events go to the shared sink, tenant sink, audit sink, and alert sink; avoid duplicating the same exception unnecessarily.
- **Async appenders:** if a filter sits after the queue, processing may be delayed; ensure the event captures context before leaving the producer. Context filtering does not replace backpressure or queue-overflow handling.
- **Redaction:** a filter decides whether to drop or keep the whole event; it **does not automatically mask tokens, passwords, or PII** inside kept events. Redaction requires a dedicated mechanism before logging or in an appropriate encoder/pipeline stage.

## 10. How to test context-based filtering

Write tests at the **log receiving point** (a capturing appender or test handler) rather than merely asserting that `logger.info(...)` was called. Minimum test cases:

1. Event matching `tenantId=tenant-a`: the TENANT_A sink receives exactly one event.
2. Event mismatching `tenantId=tenant-b`: the dedicated sink receives nothing; the shared sink still receives it when the level allows.
3. Event with missing/null context: the dedicated sink rejects per policy; the shared sink records an appropriate diagnostic.
4. Event below logger level: dropped even when the tenant matches; proves logger level and appender filter are separate layers.
5. Thread pool with **a single worker**: run task A, then B, then a task without a tenant; verify A's context does not leak into B or the final task.
6. Async event: create an event while tenant=A, then change the producer's MDC to B before the writer processes it; the earlier event must still be processed with the captured A context.
7. Exceptions and shutdown: critical WARN/ERROR events still have a reliable write path, even when a tenant-specific sink rejects them.
8. Multiple filters: verify actual `ACCEPT`/`DENY`/`NEUTRAL` outcomes at the exact stages (global/logger/appender) and compare against the approved decision table.

Do not assert log ordering across multiple threads unless the scheduler guarantees it. Use `taskId`/`requestId` and event codes for correlation. For Logback/Log4j 2 XML configurations, integration tests must run with the application's actual backend and version, because a well-written config file that is never loaded has no effect.

### Metrics to monitor

When filters are used for volume reduction or routing, measure log volume **before and after** each rule, missing-context frequency, queue drops, appender errors, and record counts in shared vs. dedicated sinks. A sudden spike in events missing `tenantId` often indicates a context-propagation bug across an async boundary rather than a drop in valid traffic.

## 11. Common issues and fixes

| Symptom | Common Cause | How to Verify and Fix |
| --- | --- | --- |
| `%X{tenantId}` is empty | MDC was not set, logging on another thread, or context cleared too early | Check boundaries and per-task MDC snapshots |
| Tenant appears in message but filter does not match | Filter reads metadata, while message is just a string | Put `tenantId` into MDC/context map properly |
| A's logs appear in B's file | Stale MDC on thread pool or untrusted tenant ID | Clear in `finally`, validate tenant, and test thread reuse |
| Missing ERRORs when tenant is absent | `DENY` filter placed too broadly/globally | Keep a reliable shared sink; filter only the dedicated sink |
| DEBUG is missing even though tenant matches | Logger level or another filter blocked it | Check logger configuration and every filter stage |
| Same event appears multiple times | Appender attached twice or unintended additivity | Check appender refs, parent loggers, and additivity |
| Filter has no effect | Config not loaded, wrong class/backend, wrong key or filename | Check startup diagnostics, classpath, and effective config |
| Logs show wrong tenant after async callback | Callback did not receive the original context | Propagate snapshot across every async boundary |
| Logs lost when queue is full | Async appender discard policy | Monitor drops/backpressure; do not blame everything on the context filter |
| Selecting tenant via `message.contains(...)` | Relies on fragile text or user-controlled input | Switch to a controlled context field |

## 12. Practical adoption checklist

Before introducing context-based filtering into an application:

1. Define the **goal** clearly: drop noisy logs, select logs for debugging, or route to dedicated sinks; do not use one configuration for three different goals.
2. Choose **keys and trusted sources**; standardize field names and rules for missing/mismatched values.
3. Determine the **stage**: global/turbo to drop early, appender-level to affect individual sinks. Write a decision table covering INFO/DEBUG/ERROR and each context value.
4. Scope context to the request/job; propagate and clean up across every async boundary.
5. Maintain a **shared log/incident path** per system policy, especially for unexpected errors.
6. Write unit tests for match/mismatch/missing, then integration tests with the real backend and reused thread pools.
7. Monitor accepted/dropped log counts, performance, and query isolation in the collection system.

**Remember:** a context filter uses event metadata to select logs for the right context. Filtering at the appender lets you keep a shared log channel while adding selective channels. MDC values must be set properly, propagated across async boundaries, and cleaned up; filters do not replace log levels, redaction, or access control.

### Official references

- Logback — [Filters](https://logback.qos.ch/manual/filters.html) and [Mapped Diagnostic Context](https://logback.qos.ch/manual/mdc.html).
- Apache Log4j 2 — [Filters](https://logging.apache.org/log4j/2.x/manual/filters.html) and [Thread Context](https://logging.apache.org/log4j/2.x/manual/thread-context.html).
- SLF4J — [MDC API](https://www.slf4j.org/api/org/slf4j/MDC.html).
- Java 17 — [java.util.logging.Filter](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Filter.html), [Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html), [LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html).