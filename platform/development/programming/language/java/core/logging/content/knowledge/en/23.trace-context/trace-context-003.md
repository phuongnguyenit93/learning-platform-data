# Trace context in logs (Java Core Logging)

## 1. Why do logs need trace context?

In a Java application serving many concurrent requests, logs from multiple threads and services are often interleaved. Looking only at timestamps, INFO/ERROR levels, and messages makes it difficult to tell which log lines belong to the same execution flow. **Trace context in logs** is a set of identifiers attached to each log event to trace the entire path of a task, especially when the task spans multiple services or runs asynchronously.

For example, two log lines in two services sharing the same trace ID help locate events belonging to one processing chain:

~~~text
INFO  service=api     trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=00f067aa0ba902b7 - Accepted order
INFO  service=payment trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=1111111111111111 - Charged order
~~~

The value of this approach is the ability to filter logs by trace ID when investigating errors, correlate logs with distributed traces, and reduce confusion between concurrent requests. Context does not replace clear log messages, exception stack traces, or an actual tracing system.

## 2. Identifiers to distinguish

| Field | Meaning | Scope |
| --- | --- | --- |
| trace_id | Identifier for the entire trace, remaining constant as the same trace traverses multiple spans/services | A distributed trace |
| span_id | Identifier of the active span at the time the log is created; different steps can have different span IDs | A single span |
| parent_span_id | Parent span of the current span, useful for representing parent–child relationships; not required in every log line | Relationship between spans |
| request_id / correlation_id | Identifier defined by the application or gateway for looking up a request/business flow; does not automatically conform to a trace ID standard | System-dependent |
| trace_flags | Flags of the trace context, where the sampled bit indicates the tracing sampling decision | Trace context |
| service.name | Name of the service emitting the log, used to distinguish sources during centralized aggregation | Service |

**Trace ID and request ID are not synonymous.** An HTTP request often corresponds to one trace, but a trace may continue across a queue, or a single business flow may consist of multiple requests. Do not take an arbitrary request ID string and treat it as a W3C trace ID.

### Trace context propagation between services

W3C Trace Context defines the `traceparent` HTTP header with the following format:

~~~text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             ^^ ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ ^^^^^^^^^^^^^^^^ ^^
             │  trace-id (32 hex chars)         │                trace-flags
             version                            parent-id (16 hex chars)
~~~

In version `00`, `trace-id` is 16 bytes (32 lowercase hex characters) and `parent-id` is 8 bytes (16 lowercase hex characters); neither ID may be all zeros. When a service receives `traceparent`, `parent-id` is the sender's span ID; when the service creates a new span, its current `span_id` may differ from the incoming `parent-id`. The `tracestate` header can carry vendor-specific information. The `baggage` header, if present, is used to pass additional attributes and must be controlled for sensitive data.

~~~text
Client
  └─ traceparent ──> API [span A]
                       ├─ log: trace=T, span=A
                       └─ traceparent ──> Payment [span B]
                                             └─ log: trace=T, span=B
~~~

Both services keep the same trace ID `T` while having different span IDs `A` and `B`. Propagating `traceparent` via HTTP/message headers and creating spans are the responsibility of the tracing library or instrumentation; merely putting a value into a log does not create a distributed trace.

## 3. MDC: how to attach context to Java logs

SLF4J provides the **Mapped Diagnostic Context (MDC)** API: a string-to-string map, typically bound by the logging provider to the currently executing thread. Logback uses the `%X{key}` specifier in its pattern to retrieve the MDC value at log time.

~~~java
MDC.put("trace_id", "4bf92f3577b34da6a3ce929d0e0e4736");
try {
    logger.info("Processing");
} finally {
    MDC.remove("trace_id");
}
~~~

This is an illustrative snippet inside a class that already has a `logger`, not a standalone program. You must clean up the context in `finally` because pool threads are reused; if a value is left behind, logs from a subsequent request can be tagged with the previous request's trace ID. When scopes are nested or you need to preserve the previous context, save and restore the entire map instead of calling `clear` unconditionally.

MDC is data for logging; it **does not automatically propagate over the network, does not create spans, and is not guaranteed to carry over to `ExecutorService`, `CompletableFuture`, or reactive pipelines**. You must transfer context using an appropriate mechanism at asynchronous boundaries.

## 4. Java 17+ example: trace-correlated logging and MDC propagation to a thread pool

This example uses SLF4J 2.0.20 with Logback 1.6.5. The IDs used in the example are simulated data for learning MDC; the program does not create OpenTelemetry spans or send traces over the network.

Maven project structure:

~~~text
trace-log-demo/
├── pom.xml
└── src/main/
    ├── java/example/TraceLogDemo.java
    └── resources/logback.xml
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>trace-log-demo</artifactId>
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
            <version>1.6.5</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/resources/logback.xml**

~~~xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level trace_id=%X{trace_id:-none} span_id=%X{span_id:-none} request_id=%X{request_id:-none} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

In the pattern, `%X{trace_id:-none}` displays the MDC `trace_id`; if absent, it displays `none`. Fields are named consistently so log collection systems can search them.

**src/main/java/example/TraceLogDemo.java**

~~~java
package example;

import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class TraceLogDemo {
    private static final Logger LOG = LoggerFactory.getLogger(TraceLogDemo.class);

    // Set the context for the current scope, then restore the previous context.
    private static void withMdc(Map<String, String> context, Runnable action) {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            if (context == null || context.isEmpty()) {
                MDC.clear();
            } else {
                MDC.setContextMap(context);
            }
            action.run();
        } finally {
            if (previous == null || previous.isEmpty()) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    }

    public static void main(String[] args) {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            LOG.info("before request");

            Map<String, String> requestContext = Map.of(
                "trace_id", "4bf92f3577b34da6a3ce929d0e0e4736",
                "span_id", "00f067aa0ba902b7",
                "request_id", "req-42"
            );

            withMdc(requestContext, () -> {
                LOG.info("request accepted");

                // Capture a copy on the calling thread before submitting to the pool.
                Map<String, String> captured = MDC.getCopyOfContextMap();
                CompletableFuture.runAsync(
                    () -> withMdc(captured, () -> {
                        // Simulate another span; does not create a real span.
                        MDC.put("span_id", "1111111111111111");
                        LOG.info("async work");
                    }),
                    pool
                ).join();

                LOG.info("response sent");
            });

            LOG.info("after request");
        } finally {
            pool.shutdown();
        }
    }
}
~~~

In the directory containing `pom.xml`, using JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.TraceLogDemo
~~~

The log output produced by the application (ignoring any Maven-specific messages) appears in this exact order:

~~~text
INFO trace_id=none span_id=none request_id=none - before request
INFO trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=00f067aa0ba902b7 request_id=req-42 - request accepted
INFO trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=1111111111111111 request_id=req-42 - async work
INFO trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=00f067aa0ba902b7 request_id=req-42 - response sent
INFO trace_id=none span_id=none request_id=none - after request
~~~

**Why is this correct?** `withMdc` captures a copy of the previous context, sets the new context in `try`, and restores it in `finally`. The thread pool receives `captured` from the calling thread and restores its own MDC after the task. `join()` waits for the thread pool log to complete before logging `response sent`, so the line order in the example is deterministic. Changing `span_id` in the async task only affects that task's scope; after returning to the calling thread, the original `span_id` remains intact. The first and last lines outside the scope carry no trace ID, proving there is no MDC leak.

**Limitation of the example:** manually updating MDC `span_id` only changes the log label. When using real tracing, spans must be created/activated through a tracer; do not assign fake values to claim that a span has been recorded in the tracing system.

## 5. Integrating real tracing with OpenTelemetry

In a multi-service system, you should use an appropriate OpenTelemetry SDK or Java agent to automatically or directly handle these steps: receiving and validating `traceparent`, creating spans, maintaining the active context, propagating context when calling other services, and injecting the current span's `trace_id`/`span_id` into logs.

With the OpenTelemetry Java agent and its MDC instrumentation enabled, the common keys in a logging event are:

- `trace_id`: ID of the current trace;
- `span_id`: ID of the current span;
- `trace_flags`: flags of the current trace, e.g., `01` when sampled.

Example Logback pattern you can use:

~~~xml
<pattern>%d{ISO8601} %-5level service=orders trace_id=%X{trace_id:-} span_id=%X{span_id:-} flags=%X{trace_flags:-} - %msg%n</pattern>
~~~

This is a pattern snippet, not a complete configuration for installing the OpenTelemetry Java agent. You must configure the agent/exporter, enable the appropriate instrumentation, and verify the logging provider in use. When no valid span is active, do not assume trace fields will appear automatically. **Do not mix manual MDC assignment and agent-injected MDC on the same keys** without clearly understanding how they interact.

Practical usage model:

1. HTTP ingress extracts or initializes the trace context; the tracer establishes the current span.
2. Logs inside the service record `trace_id`/`span_id` from the current span.
3. HTTP clients or queue producers inject context into outgoing call metadata.
4. Downstream services/consumers extract context and create a child span; logs continue with the same `trace_id`.
5. On background branches, spawned tasks must carry the context explicitly (or use supporting instrumentation/framework mechanisms).
6. When a scope ends, the context is closed/restored to prevent bleeding into other tasks.

This workflow solves both **cross-service tracing** and **log-to-trace correlation**; MDC alone only handles writing context into logs.

## 6. Situations to watch out for

### Thread pools, CompletableFuture, virtual threads, and reactive flows

- Traditional MDC is typically thread-bound. Do not assume context is automatically inherited when using `ExecutorService`, `CompletableFuture`, or running callbacks on another thread.
- Use tracing or framework context-propagation wrappers/mechanisms to capture and restore context at task boundaries; always clean up context in `finally`.
- With reactive streams, a single request may switch threads many times; use Reactor/OpenTelemetry context propagation instead of setting MDC once on the initial thread.
- With virtual threads, you must still review how your logging and tracing libraries manage context; do not assume context automatically flows through every asynchronous task.

### Security and integrity

- Never put access tokens, passwords, payment details, or sensitive personal data into MDC, baggage, or logs. A trace ID is only a correlation identifier, not proof of identity authentication.
- External `traceparent` headers must be validated by the tracing library's parser; if invalid, discard them and apply your policy for starting a new trace. Never trust arbitrary client-supplied values and log them verbatim.
- Limit length and sanitize custom fields such as `request_id` to avoid newline/control characters that enable log forging.
- Use stable field names, such as `trace_id`, `span_id`, `request_id`, `service.name`; verify how your log backend searches/indexes these fields. With structured JSON logging, keep them as separate properties rather than embedding everything in `message`.
- A `sampled` decision in `trace_flags` does not mean every log line is retained, and a log containing a trace ID does not prove that the trace was exported or kept by sampling.

### Common implementation pitfalls

| Symptom | Common cause | How to check/fix |
| --- | --- | --- |
| Logs in thread pool lack `trace_id` | MDC was only set on the calling thread | Pass context into the task and restore in `finally` |
| Request B has Request A's `trace_id` | MDC was not cleaned up after a request or task | Use a `try`/`finally` scope; test two requests on the same pool |
| Multiple services share `request_id` but traces don't link | Only a custom ID is passed; missing `traceparent` and real spans | Check context inject/extract via tracing SDK/agent |
| Same `trace_id` but `span_id` never changes across steps | Child spans not created/activated, or IDs set manually | Use a tracer and verify the active span |
| Log backend shows no `trace_id` despite `MDC.put` | Pattern/appender doesn't output MDC, provider unsupported, or no active span with agent | Check SLF4J backend, Logback pattern, and instrumentation |
| Trace has `sampled=01` but is missing in backend | Pipeline/exporter error, different sampling config, not yet exported | Check SDK/exporter, collector, and sampling policy |

## 7. How to verify correct behavior

When integrating into a real application, test at least the following cases:

1. Send two concurrent requests: each request gets its own `trace_id`, and every log within each request keeps its correct ID.
2. Submit a task to `ExecutorService`/`CompletableFuture`: logs inside have the expected context, and logs of the next task on the same worker do not inherit the old context.
3. Make an API call to another service: `trace_id` matches across both services, while `span_id` reflects each service's current span.
4. Trigger an exception or timeout: context is still cleaned up in `finally`, and full exception details appear in the logs.
5. Send a malformed `traceparent`: the application handles it safely via the parser/instrumentation and does not accept an arbitrary ID as a valid trace.
6. Disable span-creating instrumentation or log outside a span: understand exactly why `trace_id` is absent and do not attach a fake ID.

Extended exercise: run three requests on a small fixed thread pool; add distinct `request_id` values and verify via logs that no request receives the wrong context. Then enable real distributed tracing, find all logs for a single `trace_id` across multiple services, and compare the corresponding `span_id` values.

## 8. Key takeaways

Trace context in logs connects related events across threads and services. **Trace ID** identifies a trace; **span ID** identifies the running span; **MDC** is how the logging framework renders these IDs in each log line. For reliable correlation, you need context propagation, scope cleanup, and proper tracing instrumentation; putting a few strings into MDC on your own is not distributed tracing.

### References

- W3C Trace Context (`traceparent`, `tracestate` specification): https://www.w3.org/TR/trace-context/
- SLF4J MDC API: https://www.slf4j.org/apidocs/org/slf4j/MDC.html
- Logback MDC manual: https://logback.qos.ch/manual/mdc.html
- Logback PatternLayout (`%X`): https://logback.qos.ch/manual/layouts.html
- OpenTelemetry Java — logger MDC instrumentation: https://github.com/open-telemetry/opentelemetry-java-instrumentation/blob/main/docs/logger-mdc-instrumentation.md