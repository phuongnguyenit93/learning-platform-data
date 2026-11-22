# Incomplete Trace Context in Java Core Logging

## Objectives

After this lesson, you will be able to recognize when a log record is missing trace correlation information, distinguish between issues at the logging layer and the distributed tracing layer, pinpoint where context is dropped during asynchronous processing, and fix it by propagating, activating, and restoring context according to the task lifecycle. The primary example uses Java 17 and the standard library to observe the issue independently; the MDC/OpenTelemetry integration snippets are clearly marked as illustrative code for applications that use those libraries.

## 1. What Does “Incomplete” Mean?

**Trace context** is information used to correlate operations belonging to the same request or workflow. A system with distributed tracing typically includes the following fields:

| Field | Meaning | When Needed |
| --- | --- | --- |
| **traceId** | Common identifier for the entire trace; related spans share the same trace ID. | Needed when you want to link logs to a trace or follow a request across multiple services. |
| **spanId** | Identifier of the current span. | Needed when logs must be tied to a specific operation/span. Child spans get a new span ID. |
| **parent span** | Parent–child relationship between spans, usually stored in span data rather than every log line. | Needed to reconstruct the trace tree accurately. Not necessarily a required field on every log line. |
| **trace flags / sampling** | Flags such as sampled, used for deciding whether to record/collect the trace. | Needed when investigating why a trace does not appear in the backend. |
| **tracestate / baggage** | Propagation-related metadata; baggage carries selected application values. | System-dependent; not a requirement for every log to be considered complete. |

A log line that has a **traceId** but is missing a **spanId** lacks span correlation if the log occurs inside an active span. A processing flow that has a completely different traceId in the next service is a sign of broken propagation. Conversely, logs during JVM startup, in an independent background task, or before a span is created can validly lack a traceId/spanId.

Distinguish between three things:

- **Active trace context**: the context held by the tracing library for the current unit of execution; used to create child spans and inject context into outgoing requests.
- **MDC (Mapped Diagnostic Context)**: a key–value map used by logging frameworks such as SLF4J/Logback to add fields to logs on the currently running thread. MDC does not create distributed traces on its own.
- **Request/correlation ID**: an application-specific ID for finding logs of the same request; useful, but does not replace traceId/spanId or parent–child span relationships.

A system may propagate trace context properly while its formatter configuration fails to include traceId in the log output. Conversely, you might copy MDC accurately to another thread without activating the tracing context; in that case, the logs appear to have a traceId while new spans or subsequent HTTP calls still lose correlation.

## 2. Symptoms and Impact

Consider an example where a request passes through an API, a task running in a thread pool, and a payment service:

~~~text
API            traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=00f067aa0ba902b7
async worker   traceId=-                                spanId=-
payment HTTP   traceId=a12c...                          spanId=...
~~~

The second line loses its information in the log; the last line illustrates a downstream service starting a different trace (the shortened values are for illustration only, not valid trace IDs for wire transmission). Both can break end-to-end request tracing, but you must inspect each boundary separately to know whether the tracing context itself was lost or only the log fields were missing.

Common symptoms:

1. Logs in the controller have a traceId, but logs in an **ExecutorService**, **CompletableFuture**, callback, listener, or scheduler are missing it.
2. Within the same request, log lines have different traceIds or a spanId that does not match the active span.
3. The tracing backend shows multiple disconnected root spans instead of a single trace with parent–child relationships.
4. Spans are still recorded, but JSON logs lack correlation fields; or the fields appear on stdout but are lost in the collection pipeline.
5. A thread pool retains the traceId from a previous request: this is **context leakage**, which is more dangerous than a blank value because it falsely links logs across different requests.

Do not conclude “propagation is broken” solely because searching for a traceId in the observability UI yields nothing: the trace might not have been sampled/exported, timestamps might be skewed, or the log pipeline might rename/filter fields.

## 3. Why Does Trace Context Go Missing?

| Handoff Point | Mechanism Causing Loss | How to Verify |
| --- | --- | --- |
| **Inbound HTTP / message consumer** | Headers/metadata are not extracted, headers are invalid, or tracing middleware did not run. | Inspect valid headers at the receiving boundary, and compare the active trace/span immediately after the extract step. |
| **Starting request processing** | A span is created without making its context active, or the scope is closed before logging/running the task. | Check the timing of span creation/activation/closing relative to when logs are written. |
| **Populating log data** | MDC has not been mapped from the current span; the logger pattern/JSON encoder does not output trace_id or span_id. | Compare the active span, MDC at the log site, and the final log payload. |
| **Thread pool / async** | ThreadLocal or MDC is bound only to the current thread; the task runs on a reused thread and does not inherit context. | Compare context at task submission time and when the task actually executes. |
| **Outbound HTTP / message producer** | Trace context is not injected into the carrier, a different propagator is used, or context is lost before sending. | Inspect the actual headers/metadata sent and the extraction on the receiving side. |
| **Collector / log pipeline** | A parser, transform, or mapping drops fields; logs and traces are filtered/sampled under different policies. | Compare raw application logs, data entering the collector, and indexed records. |

For HTTP communication using W3C Trace Context, a typical **traceparent** header looks like:

~~~text
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

The parts are, in order: version, 32-hex-digit **trace-id**, 16-hex-digit **parent-id**, and two-hex-digit **trace-flags**. Valid trace IDs and span IDs must not be all zeros; the **01** flag in the example indicates the sampled bit is set. The sender's parent-id value is the sender's span ID; the receiver can create a child span with a **new spanId**, while keeping the same traceId and parent–child relationship. **tracestate** and **baggage** are optional supplementary headers depending on the use case; their absence does not automatically mean the trace context is broken.

Do not assemble headers manually or blindly trust all external header values. Use a propagator compatible with your tracing system to extract/inject, and enforce size and trust limits on accompanying data.

## 4. Java 17 Example: Losing Context When Switching to a Thread Pool

The following example simulates log correlation fields using **ThreadLocal<Map>**. It **does not create OpenTelemetry spans** and **does not propagate W3C traceparent**; its goal is to clearly show why MDC/ThreadLocal disappears when a task runs on another thread. The program runs standalone and requires no dependencies outside the JDK.

Save as **TraceContextDemo.java**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class TraceContextDemo {
    private static final ThreadLocal<Map<String, String>> CONTEXT =
            ThreadLocal.withInitial(HashMap::new);

    private static Runnable captureContext(Runnable task) {
        // Capture a snapshot at the time the task is submitted.
        Map<String, String> captured = Map.copyOf(CONTEXT.get());

        return () -> {
            // Save the worker thread's previous context to restore after the task.
            Map<String, String> previous = CONTEXT.get();
            CONTEXT.set(new HashMap<>(captured));
            try {
                task.run();
            } finally {
                if (previous.isEmpty()) {
                    CONTEXT.remove();
                } else {
                    CONTEXT.set(previous);
                }
            }
        };
    }

    private static void log(String stage) {
        Map<String, String> data = CONTEXT.get();
        System.out.printf(
                "%s: traceId=%s spanId=%s%n",
                stage,
                data.getOrDefault("traceId", "-"),
                data.getOrDefault("spanId", "-")
        );
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            CONTEXT.get().put(
                    "traceId", "4bf92f3577b34da6a3ce929d0e0e4736");
            CONTEXT.get().put("spanId", "00f067aa0ba902b7");

            pool.submit(() -> log("withoutPropagation")).get();
            pool.submit(captureContext(() -> log("withPropagation"))).get();
            pool.submit(() -> log("afterTask")).get();
        } finally {
            CONTEXT.remove();
            pool.shutdown();
        }
    }
}
~~~

Compile and run:

~~~bash
javac TraceContextDemo.java
java TraceContextDemo
~~~

Expected output:

~~~text
withoutPropagation: traceId=- spanId=-
withPropagation: traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=00f067aa0ba902b7
afterTask: traceId=- spanId=-
~~~

Explanation:

- **withoutPropagation**: the main thread has the data, but the pool's worker thread has its own ThreadLocal and therefore does not see main's data.
- **withPropagation**: the **captureContext** method takes a snapshot at submission time, sets the snapshot on the worker while the task runs, and restores the previous context in **finally**, even if the task throws an exception.
- **afterTask**: the worker does not retain data from the previous task. This is especially important because pools reuse threads across many requests.

This is an example of **log context**. When an application actually creates a span for asynchronous work, the new span needs **its own spanId** and a reference to the appropriate parent span. Merely copying the two traceId/spanId strings in this example does not perform that step.

Note: **InheritableThreadLocal** is not a general solution for thread pools, because worker threads are usually created ahead of time and reused; inheritance at thread creation time is not equivalent to per-task propagation. Passing context when submitting/handing off the task and cleaning up upon completion is the proper way to control the boundary.

## 5. Applying to Real Loggers and Tracers

### 5.1. With SLF4J MDC

MDC is tied to the application's logging mechanism. For a task running in an executor, you can capture the MDC at the submission site and set/restore the MDC around the task:

~~~java
// Illustrative code: the application already has SLF4J, executor, and task.
Map<String, String> capturedMdc = MDC.getCopyOfContextMap();

Runnable wrapped = () -> {
    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        if (capturedMdc == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(capturedMdc);
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
executor.execute(wrapped);
~~~

This snippet requires **org.slf4j.MDC**, **java.util.Map**, and the **executor/task** variables provided by the application; it is not a standalone Java file. Do not substitute this code for a framework that already handles MDC/tracing propagation automatically unless you understand the existing mechanism, as doing so can create overlapping contexts or overwrite a valid context.

MDC only determines which fields are included in log output. If you want cross-service traces, the application also needs a tracer, propagator, and appropriate span context. MDC key names (**trace_id**, **span_id**, **traceId**, **spanId**, etc.) must match the layout/encoder and backend queries. Verify the fields **in the actual emitted logs**, not just by checking that MDC has values in a debugger.

### 5.2. With OpenTelemetry Context

In an application configured with OpenTelemetry Java, you can wrap a **Runnable** with the current context before passing it to an executor:

~~~java
// Illustrative code: OpenTelemetry Context API and executor/task are available.
Runnable wrapped = io.opentelemetry.context.Context.current().wrap(task);
executor.execute(wrapped);
~~~

The wrapper activates the captured context while the task runs and restores the scope afterward. For logs to include traceId/spanId, you also need a **log correlation/MDC bridge** configuration or corresponding instrumentation; **Context.wrap** by itself does not guarantee the encoder will print those fields. For HTTP clients/servers or message brokers, use instrumentation/propagators to **extract on the receiving side** and **inject on the sending side**, then create child spans according to tracing rules.

If you use **CompletableFuture.supplyAsync**, **thenApplyAsync**, or callbacks that switch to another executor, check every asynchronous boundary. Context on the calling thread does not automatically appear in every callback. With reactive frameworks, use the propagation mechanism provided by the framework/instrumentation; avoid relying solely on ThreadLocal when a task can switch threads.

### 5.3. Proper Context Lifecycle

~~~text
Receive request/message
    → extract remote trace context (if present and valid)
    → create/activate current span
    → map trace/span ID into logs if needed
    → capture context when crossing async boundaries
    → temporarily activate in callback/worker, creating child span when appropriate
    → inject context when calling downstream services or publishing messages
    → close scope, restore previous context, and clear MDC
~~~

Use **try/finally** or auto-closing scopes to prevent leaks. For a new request without an upstream trace context, the tracer can proactively start a new root trace; that is not an error. For data coming from untrusted systems, never allow arbitrary baggage to become log fields containing tokens, passwords, or sensitive information.

## 6. Systematic Diagnosis

When you see logs missing a traceId or spanId, follow this order to isolate the fault:

1. **Set the right expectations**: is the log actually inside a traced operation? If it is from startup or an independent scheduler, missing IDs may be normal.
2. **Check at the source**: at the log site, is a span context active and valid? If it is, yet the log lacks the fields, focus on the MDC bridge/encoder.
3. **Compare before and after async**: print or inspect the IDs right before submission and inside the Runnable/callback. Losing IDs only after this boundary is usually a propagation bug.
4. **Check network boundaries**: on inbound HTTP/messages, verify context extraction; on outbound, verify injected headers/metadata. Compare the traceId on both sides and the parent span.
5. **Separate propagation from sampling/export**: having a traceId in logs does not mean every span is collected; a trace not appearing in the backend is not enough to prove propagation is broken.
6. **Check the log pipeline**: compare console/file output → agent/collector → parsed fields → search index/dashboard. Fields can be renamed, dropped, or mistyped.
7. **Check for leaks**: after a failed task, cancellation, or completed request, run an independent task on the same pool; it must not carry the previous request's traceId.

A useful test matrix:

| Scenario | Expected Result |
| --- | --- |
| Synchronous log inside a span | Has a valid traceId and the current span's spanId, if log correlation is enabled. |
| Task in an executor with propagation | Same traceId as the parent task; spanId depends on the active span in the worker. |
| Task in an executor without propagation | Exhibits missing context like the buggy case in the example; tests catch this gap. |
| HTTP across two instrumented services | Preserves traceId; receiving span links to the correct parent, usually with a new spanId. |
| Independent root task with no remote parent | May start a new trace or no trace, depending on configuration. |
| Subsequent task on thread pool after previous task finishes | No MDC/ThreadLocal data leaked from the previous task. |
| Exception in callback | Scope/MDC is restored in finally; the error trace remains linked if the context was still valid. |
| Trace not sampled or exporter fails | IDs may still appear in logs, though spans are not necessarily in the backend. |

When writing tests, use valid fixed IDs or tracer-generated IDs—do not use shortened values like “abc...” to test W3C validators. Compare actual IDs and relationships rather than just asserting that the log string contains the word “traceId”.

## 7. Common Pitfalls When Fixing

- **Simply adding a dummy traceId when missing**: makes logs look complete but fails to link traces or leads to misattributed requests. Fix the context creation/propagation source instead.
- **Copying only MDC and assuming distributed tracing is fixed**: MDC does not create spans, inject headers, or guarantee parent–child relationships.
- **Propagating ThreadLocal only via InheritableThreadLocal**: does not properly handle worker reuse and asynchronous callbacks.
- **Failing to restore the previous context in finally**: leaks traceIds across requests on the pool, especially when exceptions occur.
- **Reusing the same spanId for every operation**: defeats span breakdown; child spans must have their own ID and appropriate parent.
- **Inferring a propagation bug just because a trace does not show up in the UI**: rule out sampling, export, and ingestion first.
- **Logging raw headers/baggage indiscriminately**: can expose sensitive data, inflate log volume, and make cardinality hard to control.

## 8. Takeaways

A trace context is considered “complete” when it contains **the right information needed for the traced operation**, survives across all processing boundaries, and is logged/displayed consistently. To fix issues, identify which step fails: **extract → activate → async propagate → log correlation → inject → export/ingest**. In Java, ThreadLocal/MDC are bound to threads, so they must be captured, activated, and restored per task. In systems with a tracer, use the tracer's propagation and scope mechanisms to maintain real traces/spans; test both **preserving the right context** and **preventing old context from leaking into subsequent tasks**.