# Sampling and Logs in Trace Context (Java Core Logging)

## 1. What problem does sampling solve?

In a system with many requests and many services, each request can generate dozens of spans and hundreds of log lines. Recording and storing all data provides detailed observability but increases CPU, network transfer, storage, indexing, and query costs. **Sampling** is a policy of keeping only a portion of observability data, according to a predetermined ratio or condition.

Three decisions need to be separated:

1. **Trace sampling:** which traces/spans are recorded and exported to the distributed tracing system.
2. **Log level and log filtering:** which events are worth logging according to `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR` levels and filters.
3. **Log sampling:** among the events that are allowed to be logged, how many lines to keep (for example, 10% of repetitive INFO logs from successful requests).

These three decisions are **not identical**. A dropped trace can still have ERROR logs; a sampled trace does not mean every DEBUG line must appear. Conversely, a log containing a `trace_id` does not guarantee that the backend is storing the corresponding trace.

For example: a service handles 100,000 requests/minute, with each request generating eight INFO logs on average. If you keep 10% of INFO log groups per request, you store approximately 80,000 instead of 800,000 INFO logs/minute, while still keeping error logs under a separate policy. The number is a statistical expectation, not a hard limit; log generation cost and traceability also depend on where the filter is applied.

## 2. Relationship between trace context and sampling

A **trace** describes the path of an operation across services. A **span** is a unit of work within a trace. **Trace context** carries identity information and sampling decision state across synchronous or asynchronous calls.

Common fields:

| Field | Meaning | Use in logs |
| --- | --- | --- |
| `trace_id` | Identifies the entire trace, typically 32 hex characters per W3C Trace Context | Connects logs from services belonging to the same request |
| `span_id` | Identifies the current span, typically 16 hex characters | Pinpoints the unit of work that produced the log |
| `trace_flags` | Flags propagated in the trace context; the `sampled` bit indicates the propagated sampling decision | Can help explain why a trace has/lacks data |
| `request_id` / `correlation_id` | Application-assigned business or request identifier | Supplements when tracing is unavailable |

According to W3C, the following header is a structurally valid `traceparent`:

```http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

The four components are version, `trace-id`, `parent-id`, and `trace-flags`, respectively. Here `01` sets the sampled bit; `00` does not set this bit. This is a **signal in the context**, not a guaranteed promise that every span will be present in storage: the exporter, Collector, or backend can still filter, reject, or drop data.

A standard flow is: receive request → extract trace context from headers → select an appropriate sampler, respecting the parent when needed → execute work, propagating context across tasks → write logs with valid `trace_id`/`span_id` → export traces and logs through separate pipelines. Do not base the decision to write all logs solely on `trace_flags.sampled`.

## 3. Trace sampling strategies

| Strategy | Where/when decision is made | Pros | Limitations |
| --- | --- | --- | --- |
| **Head sampling** | At the start of a trace or span in the SDK/ingress | Early decision, reduces the volume of spans to record/export | Cannot know in advance which request will fail or be slow; may miss important traces |
| **Parent-based head sampling** | Inherits parent decision, uses root policy for new traces | Reduces inconsistent decisions across services within the same trace | Depends on proper context propagation; downstream cannot easily recover what upstream dropped |
| **Trace ID ratio-based** | Uses deterministic distribution over the trace ID to keep a ratio, e.g., 10% | More consistent decision than flipping a coin per span | Statistical ratio; does not prioritize errors if selecting by ID alone |
| **Tail sampling** | After the Collector/processor has observed enough spans, status, or duration | Can prioritize error, slow, or rare-path traces | Consumes memory, bandwidth, and data retention time; requires proper wait time and trace routing configuration |

With 10% head sampling, roughly 10% of root traces are selected statistically; **not exactly 1 in any 10 requests**. If errors only occur in 0.1% of requests, pure ratio-based head sampling may miss many error traces. Tail sampling can keep 100% of error traces and a percentage of successful traces, but the Collector can only do that for spans that are actually sent to it. **Spans dropped at the start by the SDK cannot be recovered by a tail sampler.**

In the OpenTelemetry Java SDK, a head sampling configuration typically looks like the following illustration (a configuration snippet; requires libraries and full application SDK setup):

```java
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.samplers.Sampler;

Sampler sampler = Sampler.parentBased(Sampler.traceIdRatioBased(0.10));
SdkTracerProvider tracerProvider = SdkTracerProvider.builder()
        .setSampler(sampler)
        .build();
```

`parentBased` uses the decision from the parent when a valid parent exists; `traceIdRatioBased(0.10)` is used for new root traces at a 10% target ratio. The snippet above is not a standalone program and does not configure an exporter, processor, or shutdown lifecycle.

## 4. Log sampling strategies

**Log level is not sampling.** Disabling `DEBUG` is level-based filtering, whereas keeping 1/20 repetitive INFO logs is sampling. You can combine:

- **By event/request:** keep the entire diagnostic INFO group for a percentage of requests based on a `trace_id` hash. When a request is selected, related INFO logs have a chance to form a complete story.
- **Per line:** randomly keep 1/N similar logs. Saves evenly but can break the sequence of events within the same request.
- **Rate-based:** limit the number of identical logs per second, aggregating repetitions into a message with `suppressed_count` or a total count. Avoid masking an error spike.
- **By outcome, event type, or subject:** keep errors/slow/anomalous events in full; reduce repetitive success INFO logs. Note the cost that the outcome is only known after the request finishes.
- **By tenant or endpoint:** allocate log budgets so a high-traffic customer/route does not consume all capacity; the policy must be measured and published.

For per-request analysis, **deterministic sampling by trace ID** is usually easier to read than independent per-line selection. The hash must distribute well over actual identifiers; in a multi-service environment, you must align the ratio, key/hash, and enforcement point if you want to keep the same set of requests. Do not use the leading characters of an ID directly as a production algorithm if the ID is structured or non-random.

Reference policy (adjust according to the system's SLA and data regulations):

| Data type | Starting policy | Rationale |
| --- | --- | --- |
| Detailed `DEBUG`/`TRACE` | Off by default; enable temporarily for a narrow scope | Cost and data exposure risk |
| Repetitive `INFO` on successful requests | Sample by trace ID or aggregate | Reduces noise while still allowing inspection of normal flows |
| Investigative `WARN`/`ERROR` | Usually keep in full, with burst alerting | Prevents losing rare signals and incident root causes |
| Audit, security, mandatory transactions | Follow dedicated integrity/retention requirements; do not sample arbitrarily | May serve as evidence or policy-mandated retained data |
| Aggregate metrics | Collect independently of log sampling | Measures error rate/latency/traffic across total volume |

Not every `ERROR` needs to contain the exact same stack trace millions of times; you can limit repetitive payload, aggregate, or emit representative events according to an approved policy. However, do not let routine INFO filters accidentally hide important warnings.

## 5. Standalone Java 17 example: context propagation and INFO sampling

The example uses JDK APIs to focus on **principles**; it does not create real spans or send data to OpenTelemetry. Two requests have fixed `trace_id` values and `traceSampled` flags. The INFO filter keeps roughly 1/4 of request groups based on a portion of the ID purely for illustration; ERROR is always printed. `ThreadLocal` stores context on the executing thread, while `propagate` captures context when dispatching work to the executor and restores the previous context via `finally`.

Save the file `SamplingLoggingDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class SamplingLoggingDemo {
    private static final ThreadLocal<TraceCtx> CURRENT = new ThreadLocal<>();

    record TraceCtx(String traceId, String spanId, boolean traceSampled) {}

    private static void withContext(TraceCtx next, Runnable work) {
        TraceCtx previous = CURRENT.get();
        try {
            if (next == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(next);
            }
            work.run();
        } finally {
            if (previous == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(previous);
            }
        }
    }

    private static Runnable propagate(Runnable task) {
        TraceCtx captured = CURRENT.get();
        return () -> withContext(captured, task);
    }

    private static boolean keepInfo(TraceCtx context) {
        long prefix = Long.parseUnsignedLong(
                context.traceId().substring(0, 8), 16);
        return prefix % 4 == 0;
    }

    private static void log(String level, String event) {
        TraceCtx context = CURRENT.get();
        if ("INFO".equals(level)
                && context != null
                && !keepInfo(context)) {
            return;
        }
        String traceId = context == null ? "-" : context.traceId();
        String spanId = context == null ? "-" : context.spanId();
        String sampled = context == null
                ? "-" : Boolean.toString(context.traceSampled());
        System.out.printf(
                "%s trace_id=%s span_id=%s trace_sampled=%s event=%s%n",
                level, traceId, spanId, sampled, event);
    }

    private static void handle(TraceCtx context, ExecutorService pool) {
        withContext(context, () -> {
            log("INFO", "start");
            CompletableFuture.runAsync(
                    propagate(() -> log("INFO", "async_work")), pool
            ).join();
            log("ERROR", "simulated_failure");
        });
    }

    public static void main(String[] args) {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            handle(new TraceCtx(
                    "00000004000000000000000000000001",
                    "000000000000000a", false), pool);
            handle(new TraceCtx(
                    "00000005000000000000000000000002",
                    "000000000000000b", true), pool);
        } finally {
            pool.shutdown();
        }
    }
}
```

Compile and run:

```bash
javac SamplingLoggingDemo.java
java SamplingLoggingDemo
```

Stdout output (excluding the command prompt):

```text
INFO trace_id=00000004000000000000000000000001 span_id=000000000000000a trace_sampled=false event=start
INFO trace_id=00000004000000000000000000000001 span_id=000000000000000a trace_sampled=false event=async_work
ERROR trace_id=00000004000000000000000000000001 span_id=000000000000000a trace_sampled=false event=simulated_failure
ERROR trace_id=00000005000000000000000000000002 span_id=000000000000000b trace_sampled=true event=simulated_failure
```

Explanation:

1. The first trace has prefix `00000004`, so `4 % 4 == 0`: both INFO logs are kept, **even though** `traceSampled=false`.
2. The second trace has prefix `00000005`, so INFO logs are filtered out, **even though** `traceSampled=true`.
3. Both ERROR logs still appear. This is a **simulated error event to illustrate logging**; the program does not throw an exception.
4. In the task running on the pool thread, `propagate` transfers the trace context to the logging point. After the task finishes, `finally` restores the previous context so it does not leak to another request.

The example intentionally uses a prefix and hardcoded IDs so stdout can be verified. **Real applications** must use valid IDs and a stable hash algorithm over the full ID (or an SDK/Collector policy), and use context propagation mechanisms supported by the tracing library rather than building a distributed tracing system from `ThreadLocal` yourself.

## 6. Implementation with SLF4J, MDC, and OpenTelemetry

In Java, logs are typically emitted through SLF4J with Logback/Log4j2 or another backend. **MDC (Mapped Diagnostic Context)** attaches contextual information to each log event, such as `trace_id` and `span_id`. MDC is typically thread-bound, so it does not automatically follow `CompletableFuture`, executors, or callbacks; tracing platforms provide context propagation/instrumentation mechanisms to solve this.

For applications already instrumented with OpenTelemetry, prefer the trace/span ID injection and context propagation features of your current stack. The snippet below only illustrates reading the current span and adding two MDC fields for the scope of a single log; it requires OpenTelemetry API, SLF4J, and an existing logger:

```java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;
import org.slf4j.MDC;

SpanContext spanContext = Span.current().getSpanContext();
if (spanContext.isValid()) {
    try (MDC.MDCCloseable trace = MDC.putCloseable(
                 "trace_id", spanContext.getTraceId());
         MDC.MDCCloseable span = MDC.putCloseable(
                 "span_id", spanContext.getSpanId())) {
        logger.info("Order processed");
    }
}
```

Only add IDs when the context is valid; configure the encoder/layout so MDC fields are actually output in JSON or text logs. `MDCCloseable` cleans up values after logging, preventing stale data from a previous request from remaining on a reused thread. If an agent/instrumentation already injects trace context automatically, do not insert duplicates or create conflicting keys.

Clarify where the sampler sits in the pipeline:

```text
HTTP/gRPC request
  -> extract/propagate trace context
  -> application + spans
       |-> trace SDK/exporter -> (head/tail sampling) -> trace backend
       |-> logger/MDC -> level/filter/log sampling -> log backend
  -> metrics (counts all traffic, errors, latency)
```

Exact ordering and placement vary by stack. If log sampling is performed in the application, dropped logs are not sent over the network; if filtering happens at the collector/backend, the application may still incur the cost of generating and transmitting logs. Use parameterized logging, such as `logger.debug("id={}", id)`, to avoid unnecessary string concatenation; expensive computations to build a payload should still be guarded behind log-level checks when appropriate.

## 7. Designing a policy without losing investigability

A useful policy must answer:

1. **What must always be kept?** Typically critical error signals, mandatory audits, security detections, payment incidents, or events with dedicated retention requirements.
2. **What can be reduced?** Repetitive success INFO logs, high-frequency diagnostic details, duplicate stack traces that add no new information.
3. **Where should sampling happen?** In the SDK/logger, gateway/Collector, or backend? This decision affects costs before and after the filtering point.
4. **What is the sampling unit?** By request/trace, event, endpoint, tenant, or rate limit. Rules must not break the link between logs and context.
5. **Is loss measured?** Track dropped logs/spans, export volume, exporter errors, quotas, latency, and error rates from independent metrics.

Common design mistakes and fixes:

| Mistake | Consequence | Proper approach |
| --- | --- | --- |
| Logging only when `spanContext.isSampled()` | May lose ERROR logs for unsampled traces | Base log policy on severity and investigative goals, independent of the sampled flag |
| Each service decides sampling arbitrarily | Fragmented traces/logs that are hard to correlate | Propagate parent context and align policy by trace ID |
| Using tail sampling after head sampling already dropped spans | Cannot rescue error traces already lost at the source | Ensure data needed for tail decisions reaches the tail processor |
| Forgetting to propagate context across executors | Async logs lose `trace_id` or carry the wrong ID | Use context-aware executors/instrumentation; always restore context |
| Using unstable hashes/seeds or sampling each log independently | Hard to reproduce decisions, breaks related INFO sequences | Use a consistent hash function and policy; consider per-request sampling |
| Relying on sampled logs to calculate error rates | Metrics are skewed by the sample set | Measure traffic, errors, and latency with independent metrics |
| Putting tokens, passwords, or sensitive data into MDC/baggage | Unintended data leakage or propagation | Only include safe identifiers; scrub data and set retention policies |
| Turning `trace_id` into a metric label | Very high cardinality, high cost | Keep trace IDs in logs/traces; use bounded labels for metrics |

For a request without a stored trace, `trace_id` in logs is still useful for grouping events. A trace lookup UI may return "not found" because the trace was not sampled, was dropped at the exporter, exceeded quota, or has not yet been ingested. Therefore, fields such as service, environment, severity, timestamp, `trace_id`, `span_id` (when valid), and request/operation name are needed to search logs without depending on the trace backend.

## 8. Verification in a real environment

Set up a minimal test suite: successful requests with and without trace sampling; error/timeout requests; requests spanning multiple services; asynchronous tasks on a thread pool; requests without an incoming `traceparent`; high request volume producing many identical logs. Verify:

- Logs still have the correct `trace_id`/`span_id` when context is valid; IDs do not mix between requests in a thread pool.
- Trace/log ratios **approximately** match targets over a sufficiently large sample; critical error scenarios are not filtered out by INFO policies.
- WARN/ERROR, audit, and metrics follow dedicated retention/security rules; do not rely on trace sampling to decide everything.
- Querying logs by trace ID still works even when the trace does not exist in the backend; when the trace is present, timestamps and span IDs match logically.
- Dashboards include metrics for dropped events, sampling rate, exporter failures, and volume limits to tune policies based on data.

**Key takeaway:** trace sampling controls tracing data volume, log sampling controls log lines, and trace context links the two. Selectively reducing data while preserving correlation IDs, critical error signals, data protection, and complete metrics is what creates an observability system that is both cost-effective and investigable.
