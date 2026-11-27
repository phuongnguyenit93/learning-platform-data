# Span Error in Distributed Tracing: Recording Failures and Interpreting Status Accurately

> **Chapter:** Tracing  
> **Lesson:** Span error  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learning context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production.

## 1. Scenario: HTTP 200 Yet an Inner Span Failed

The `order-api` service handles an order creation request and calls `inventory-api` to reserve stock. When inventory times out, `order-api` may use a fallback result and return HTTP 200 to the customer, yet an internal operation genuinely failed. Looking solely at the HTTP response status code, an operator could miss the problem.

A sample trace:

~~~text
Trace: POST /orders                             210 ms    HTTP 200
└── Span: orders.create                         205 ms    UNSET
    ├── Span: inventory.reserve                 180 ms    ERROR
    │   └── Event: exception (TimeoutException)
    └── Span: orders.fallback                     8 ms    UNSET
~~~

**Span error** marks the **failure of an observed operation**, instead of inferring errors solely from the final status of the entire request. Typically we want to know:

- Which operation failed, when, and how long did it take?
- Does the span carry `ERROR` status, an exception event, or merely a business tag saying "failed"?
- Why did a child span fail while the parent span succeeded or lacked an error status?
- When using Micrometer Observation in Spring Boot, how does the tracing handler process `observation.error(ex)`?
- Why do metrics report errors while the tracing backend shows no matching error span?
- How should attributes, logs, and context propagation be recorded to investigate without leaking sensitive info?

This lesson focuses on the **semantics of errors on spans**, safe instrumentation, and verification across a Spring Boot system with Micrometer Observation/Tracing.

## 2. Span, Trace, and Error Status Are Distinct Concepts

In distributed tracing, a **trace** represents the execution path of a task across multiple components. Each **span** represents an operation with start/end timestamps, name, span kind, parent, attributes, events, and status.

| Component | Role | Example |
| --- | --- | --- |
| `traceId` | Connects spans belonging to the same trace | A request traversing three services |
| `spanId` | Identifies a single span | The specific inventory call step |
| `parentSpanId` | Parent–child relationship | HTTP client span is a child of the order business step |
| `span.kind` | Role of the span | SERVER, CLIENT, INTERNAL, PRODUCER, CONSUMER |
| `span.status` | Concluding status of **this span** | UNSET, ERROR, or OK |
| `span.attributes` | Metadata describing the operation | `http.request.method=POST`, `server.address=...` |
| `span.events` | Events occurring while the span is active | Event recording an exception |
| `span.duration` | Interval from start to end | 180 ms |

A span is not a log, and a trace is not a Counter metric. Spans provide the causal–temporal structure of a single execution; metrics aggregate error rates/latency across many runs, and logs supply detailed event context. All three signals can be linked by time and trace context when configured properly.

**Do not equate "trace has an error" with "every span in the trace errored".** Each span has its own status. One span may fail and be recovered higher up, or a parent span may fail due to its own logic while child spans finish normally.

## 3. OpenTelemetry Span Status: UNSET, OK, and ERROR

In OpenTelemetry, span status generally has three codes:

| Status Code | Practical Meaning | Example |
| --- | --- | --- |
| `UNSET` | No explicit error/success status set; default state | A span completing normally without SDK/instrumentation explicitly marking `OK` |
| `OK` | Explicit success | Instrumentation explicitly determines the operation succeeded |
| `ERROR` | Operation considered failed | Timeout calling a dependency, unhandled technical error within the operation scope |

**`UNSET` does not mean "never ran" or "missing data".** Many successfully completed spans remain `UNSET` because systems only need to explicitly flag failures. When reading dashboards, never count every `UNSET` as an error.

`ERROR` may include a status description free of sensitive information; do not arbitrarily copy full exception messages into descriptions. Depending on instrumentation and backend, UIs may display these fields differently.

Example using the OpenTelemetry API directly:

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;

Span span = Span.current();

try {
    callInventory();
} catch (RuntimeException ex) {
    span.recordException(ex);
    span.setStatus(StatusCode.ERROR, "inventory call failed");
    throw ex;
}
~~~

**Important point:** `recordException(ex)` records an **exception-related event**, whereas `setStatus(StatusCode.ERROR, ...)` sets the **span status**. In the OpenTelemetry API, never assume recording an exception event automatically marks the span `ERROR`. High-level instrumentation may perform both, which is that instrumentation's responsibility.

`Span.current()` is only useful when an **active span** exists in context; without valid tracing context, it may be a no-op span. Furthermore, call this API directly only when the application genuinely uses the OpenTelemetry API and an appropriate instrumentation boundary has been chosen. Do not create an extra span around work already instrumented by Micrometer Observation.

## 4. How Do Span Status, Exception Events, and Outcome Tags Differ?

These three data points often appear side by side yet answer different questions:

| Data | Where Does It Live? | Interpretation |
| --- | --- | --- |
| **Span status** | Span status field | Was the operation judged failed under instrumentation policy? |
| **Exception event** | Span events list | A concrete exception occurred; usually has error type and controlled details |
| **Outcome attribute** | Span attribute or Micrometer low-cardinality key–value | Business outcome: `success`, `rejected`, `error` |
| **HTTP status code** | Attribute on HTTP client/server span | Protocol returned 200, 404, 500… |
| **Log level** | Log record | Severity/event level in the logging pipeline |

Valid combinations can occur:

1. Span has `ERROR` and an exception event: technical failure with recorded exception details.
2. Span is `ERROR` without an exception event: an HTTP call returned an error status or an operation was marked failed without throwing a Java exception.
3. Span is `UNSET` with an exception event: the exception was caught and recovered, or instrumentation recorded the event without setting status.
4. Span is `UNSET` and `outcome=rejected`: valid business rule rejection, not necessarily an infrastructure error.
5. HTTP 200 yet a child span is `ERROR`: fallback or internal error recovery occurred.
6. HTTP 500 without an exception event: server returned an error status without throwing an exception in code.

Therefore, **do not determine failure solely from the presence of an exception event, an ERROR log, or a single HTTP status value**. Cross-check span kind, operation semantics, and instrumentation policies.

## 5. Micrometer Observation.error(ex): Path From a Java Error to Tracing

Spring Boot typically uses **Micrometer Observation** as a unified instrumentation layer bridging metrics and tracing. When business code encounters an exception that should fail the observation, the standard API is:

~~~java
observation.error(ex);
~~~

Conceptually, the lifecycle proceeds as follows:

~~~mermaid
sequenceDiagram
    participant App as PaymentService
    participant Obs as Observation
    participant Registry as ObservationRegistry
    participant Handler as Tracing ObservationHandler
    participant Tracer as Tracer/Span
    App->>Obs: createNotStarted(...)
    App->>Obs: start()
    Obs->>Handler: onStart(context)
    Handler->>Tracer: create/start span when configured
    App->>Obs: openScope()
    Note over App: business operation throws exception
    App->>Obs: error(exception)
    Obs->>Handler: onError(context)
    Handler->>Tracer: record error on span per bridge/handler
    App->>Obs: closeScope()
    App->>Obs: stop()
    Obs->>Handler: onStop(context)
    Handler->>Tracer: end span
~~~

Points to distinguish:

- `observation.error(ex)` **notifies the Observation of an exception** so handlers receive the corresponding callback and inspect the error in context. It does not automatically emit an application log.
- A matching **Tracing ObservationHandler** can record the exception and/or mark the span failed via the Micrometer Tracing–OpenTelemetry/Brave bridge. Exact behavior and emitted attributes must be verified per version, handler, and exporter.
- A **Meter ObservationHandler** may use metadata/outcomes to build time series; calling `error(ex)` alone does not guarantee every Timer automatically gets `outcome=error` matching your domain contract.
- `observation.stop()` must still be called to complete the observation. Failing without stopping can prevent duration measurements and spans from finishing cleanly.
- `openScope()` establishes the current context for the thread/execution chain; it does not automatically catch and propagate every exception across the whole system.

If a framework already auto-instruments and records exceptions on the same observation, recording the error a second time can emit duplicate events. Clarify who owns instrumentation at each boundary.

## 6. Spring Boot Code Pattern: Instrumenting a Technical Error Once

Scenario: a payment authorization service measures a `payments.authorize` call. An exception from the gateway is a **technical error**; a payment decline decision may be an **expected business outcome**.

~~~java
package example.payment;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.function.Supplier;
import org.springframework.stereotype.Service;

@Service
public class PaymentAuthorizationService {
    private final ObservationRegistry observationRegistry;

    public PaymentAuthorizationService(
            ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public <T> T authorize(String incomingChannel, Supplier<T> operation) {
        Observation observation = Observation.createNotStarted(
                "payments.authorize", observationRegistry)
            .contextualName("authorize payment")
            .lowCardinalityKeyValue(
                "channel", normalizeChannel(incomingChannel))
            .start();

        try (Observation.Scope scope = observation.openScope()) {
            T result = operation.get();
            observation.lowCardinalityKeyValue("outcome", "success");
            return result;
        } catch (BusinessDeclinedException ex) {
            // Expected decline: business classification, not automatically treated as
            // a system error on this span.
            observation.lowCardinalityKeyValue("outcome", "declined");
            throw ex;
        } catch (RuntimeException ex) {
            observation.lowCardinalityKeyValue("outcome", "error");
            observation.error(ex);
            throw ex;
        } finally {
            observation.stop();
        }
    }

    private static String normalizeChannel(String input) {
        if ("web".equals(input)) return "web";
        if ("mobile".equals(input)) return "mobile";
        if ("partner".equals(input)) return "partner";
        return "other";
    }

    public static final class BusinessDeclinedException
            extends RuntimeException {
        public BusinessDeclinedException(String message) {
            super(message);
        }
    }
}
~~~

In this example:

- `payments.authorize` is the **business observation name**, not an HTTP server metric.
- `outcome=success/declined/error` is low-cardinality metadata for grouping metrics; never put exception messages, user IDs, or order IDs into metric tags.
- On technical errors, `observation.error(ex)` notifies the tracing handler; `throw ex` preserves the application's exception flow.
- `finally` guarantees `stop()`, and `try-with-resources` closes the scope along both success and error branches.
- On business declines, the snippet only sets `outcome=declined`. It does **not** automatically mark the business span `ERROR`; this is a policy decision that should match actual requirements.
- If `BusinessDeclinedException` escapes the controller and becomes an HTTP 500, outer HTTP server instrumentation may still mark the **server span** as an error. Map expected declines to an appropriate response (e.g., HTTP 409/422 per API contract) to preserve consistent semantics.

This is a **synchronous** example. With futures or Reactor, track when errors actually happen and how context propagates; never call `stop()` right after merely submitting work.

### 6.1. Why Not Set "error" Upfront at Start?

You cannot know in advance whether an operation will succeed or fail. Writing `outcome=error` at `start()` and never updating it marks every measurement as failed. Once the outcome is known, attach it **before `stop()`**. In some handlers, metadata read in `onStart` differs from metadata read in `onStop`; if an attribute must be present from the start, attach only values already known, never guess the outcome.

## 7. Configuring Spring Boot to Receive Span Errors in the Backend

The example below targets Spring Boot 3.x with the Micrometer Tracing bridge to OpenTelemetry. Specific dependencies and properties may vary by minor version, backend, and exporter choice.

### 7.1. Illustrative Maven Dependencies

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>
    <dependency>
        <groupId>io.opentelemetry</groupId>
        <artifactId>opentelemetry-exporter-otlp</artifactId>
    </dependency>
</dependencies>
~~~

When a project uses a compatible Spring Boot BOM/parent, dependency versions are managed automatically. Adding Actuator alone does not guarantee traces reach a Collector: you also need a tracing bridge, matching SDK/exporter, and target endpoint.

### 7.2. application.yml for Learning Environments

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

- `management.tracing.sampling.probability=1.0` illustrates keeping nearly all traces in a test environment for easy observation. **Never default to 100% sampling in production** without evaluating traffic, data value, and cost.
- `management.otlp.tracing.endpoint` configures the OTLP traces destination in this Spring Boot 3.x example. Check the exact namespace and config for your running version.
- In Docker/Kubernetes, `localhost` points to the local network namespace. If the Collector is another service, use the deployment environment's reachable hostname/address.
- `/actuator/metrics` is the metrics endpoint, **not a trace viewer endpoint**. Traces are typically viewed in an OTLP-capable system like Jaeger/Tempo or a matching commercial backend.

If your app uses the Brave bridge or another exporter, export and propagation mechanics may differ. The goal of this lesson is **understanding span errors**, not tying every system to one fixed backend.

## 8. HTTP Status and Span Error: Never Map Mechanically

HTTP status communicates protocol outcome; span status communicates whether the observed operation failed per instrumentation rules. Rules can depend on **span kind** and semantic conventions.

| Scenario | HTTP Status | Typically Reasonable View | Notes |
| --- | --- | --- | --- |
| Server succeeds | 200/201/204 | Server span normally not error | No need to manually set `OK` on every call |
| Client sends invalid request | 400 | Server may treat as expected response, not internal error | Client span may evaluate differently per semantic conventions |
| Resource not found | 404 | Could be domain outcome or client-side error | Check endpoint contract and span kind |
| Unhandled server error | 500/503 | Server span usually marked `ERROR` | May lack an exception event |
| Gateway timeout | 504 or client exception | Client span may be `ERROR` | Inspect timeout, retry, propagation |
| HTTP 200 via fallback after downstream failure | 200 | Server span may be non-error; child span may be `ERROR` | Do not assume the entire trace succeeded cleanly |
| Business rejection mapped to 409/422 | 409/422 | May be an expected business outcome | Distinguish `outcome=declined` from technical errors |

OpenTelemetry HTTP semantic conventions specify versioned rules for marking status on client/server spans. A general rule of thumb: **server-side 5xx is usually an error**, while **4xx on the server should not be conflated with an internal server error**; client-side classification may differ. Check your active instrumentation and semantic conventions rather than setting `ERROR` on every status ≥ 400.

### 8.1. Must a Business Failure Always Be a Span Error?

No. A "credit limit check" returning `insufficient_funds` may be operating **strictly per contract** even though payment wasn't approved. If the operational goal is tracking decline rates, attaching a bounded tag like `outcome=declined` is usually more useful than treating every rejection as a system failure.

Conversely, if a step is defined as "execute a successful payment request", failing to meet that goal might be classified as an error under another contract. **Rules must be consistent**, documented, and aligned with dashboards/SLOs; avoid letting each service guess from exception names.

## 9. Parent and Child Spans: Error Status Does Not Automatically Propagate

Consider a three-service path:

~~~mermaid
flowchart TD
    A["order-api: HTTP SERVER, UNSET"] --> B["orders.create: INTERNAL, UNSET"]
    B --> C["inventory-api call: CLIENT, ERROR"]
    C --> D["inventory-api: HTTP SERVER, ERROR"]
    B --> E["fallback: INTERNAL, UNSET"]
    E --> F["order-api returns fallback result"]
~~~

In a properly propagated trace, spans connect via trace context such as `traceparent`, sharing a trace ID and parent–child links. However:

- **Status is not "automatically inherited"** from child to parent. A failing child span does not force the parent span to become `ERROR`.
- A parent may **recover from an error** and finish normally; keeping `UNSET`/OK on the parent is appropriate when its contract is satisfied.
- Conversely, a parent may be `ERROR` due to a violated business invariant even when every individual downstream call succeeded.
- A downstream service span may have a different status from the caller's client span because they observe **two sides of the same exchange**, each per its own instrumentation and semantics.
- Losing trace context splits spans into disconnected traces; that is a **propagation** failure, not necessarily a status-marking failure.

When investigating, inspect the **entire waterfall** and where `ERROR` spans appear instead of only looking at the root trace icon or counting red spans.

## 10. Exception Events: What Should Be Recorded?

An exception event may carry fields such as exception type, message, stack trace, or other metadata depending on the tracing SDK, semantic conventions, and instrumentation config. Not every backend displays all fields, and not every failure has a Java stack trace.

Example event:

~~~text
span: inventory.reserve
status: ERROR
event.name: exception
exception.type: java.util.concurrent.TimeoutException
exception.message: downstream call timed out
event.time: 2026-11-22T...
~~~

This is a **structural illustration**, not a mandatory JSON schema or guaranteed output of every exporter.

### Safety Principles

- Never send access tokens, session cookies, card numbers, passwords, secret keys, or raw request/response payloads into span attributes/events.
- Never attach full exception messages automatically as **low-cardinality metric tags**: messages can vary per request, exploding series and leaking data.
- To group errors, use bounded error categories such as `error.type=timeout`, `outcome=error`, or normalized, approved exception names.
- If capturing stack traces, use appropriate sampling and retention; stack traces can be large and expose internal details.
- Never put per-order IDs or request IDs into metric labels. Technical identifiers can live in logs/trace attributes under security policies when lookup is required.
- Avoid recording the exact same exception on multiple spans without reason: one exception bubbling through layers can generate multiple events/log records, adding noise and cost.

**Important:** the goal is helping investigators understand what failed, not capturing every piece of data from every exception without control.

## 11. Why Can Status Be ERROR Without an Exception Event?

Several completely normal cases cause this:

1. **Protocol-level failure:** an HTTP client receives 503 or gRPC returns an error status without necessarily throwing a Java exception at the instrumented boundary.
2. **Explicit status setting:** code calls `setStatus(ERROR)` for a failure condition without calling `recordException`.
3. **Partial instrumentation recording:** the bridge/handler/backend represents failure via status and attributes without creating an exception event.
4. **Filtered or capped events:** the trace SDK/backend enforces event count/size limits, or the pipeline filters metadata.
5. **Outer-layer span:** the framework marks an HTTP server span as error when returning HTTP 500, even if an internal exception was already translated into a response.

And the reverse: having an exception event does not require status `ERROR`. For example, an exception is caught and retried successfully; instrumentation may record an event for the failed attempt on the span while keeping the final outcome consistent with that span's contract.

**How to verify:** inspect status code, exception events, `http.response.status_code` (or the equivalent attribute for your semantic conventions), span kind, and operation name. Never rely on a single indicator to deduce root cause.

## 12. Diagnosing Through Metrics, Logs, and Traces

In a Spring Boot application, the three signals play distinct roles:

~~~mermaid
flowchart LR
    A["Metrics: 5xx rate, latency spike"] --> B["Select service / route / timeframe"]
    B --> C["Traces: ERROR spans and child spans"]
    C --> D["Logs: traceId/spanId, exception"]
    C --> E["Span attributes: dependency, HTTP status"]
    D --> F["Root cause hypothesis"]
    E --> F
    F --> G["Remediate and verify on metrics"]
~~~

### 12.1. Metrics: Detect and Quantify

For example, an HTTP server Timer exported to Prometheus commonly produces `http_server_requests_seconds_count`. If `outcome=SERVER_ERROR` is present and matches actual data, an illustrative error-rate query is:

~~~promql
sum(rate(http_server_requests_seconds_count{
  outcome="SERVER_ERROR"
}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
~~~

The result is a ratio from 0 to 1 when the denominator is positive. This is the **convention-defined HTTP server error rate**, not automatically the ratio of spans with status `ERROR`, nor does it include failures masked behind a 200 fallback.

To measure domain errors, emit metrics with explicit semantics, such as `payments.authorize` with `outcome=error/declined/success`. Never assume `observation.error(ex)` automatically sets labels matching your SLI.

### 12.2. Logs: Detailed Evidence

When tracing integration and logging pattern/MDC are configured, logs can carry `traceId` and `spanId`. Illustrative example:

~~~text
WARN [traceId=8b... spanId=7f...] Inventory timeout after 180 ms
~~~

Logs are not emitted automatically simply because a span has status `ERROR`. A handler might record an exception event without logging; conversely, the application might log an error without notifying Observation. Consistent log correlation connects the two signals.

### 12.3. Traces: Where Failure Happened and Propagation Path

Open a sampled/exported trace, locate the **earliest `ERROR` span along the relevant path**, and examine preceding/subsequent call spans, exception events, deadlines/timeouts, retries, and fallbacks. The "earliest error span" is not always the root cause, though it is a reasonable starting point for forming hypotheses.

For instance, a request with two retries where the first failed and the last succeeded may show two client spans (one `ERROR`, one `UNSET`) while the parent business span succeeded. **Counting error spans does not equal counting failed requests** when retries occur.

## 13. Sampling, Exporters, and Why Error Traces May Not Appear

A typical pipeline:

~~~text
Observation / instrumentation
  → Tracing ObservationHandler
  → Tracer + Span
  → Sampling decision
  → Span processor / exporter
  → OTLP Collector
  → Tracing backend
  → Search / UI / retention
~~~

Reasons an error span may not be visible:

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Metrics show errors, tracing UI has no matching trace | Head sampling did not select the trace; separate data pipelines | Check sampling probability and tracing backend |
| Trace has root span, missing child client span | Uninstrumented HTTP client, lost context, different instrumentation | Check client/builder, propagation, and span kind |
| Trace exists, yet span status is not ERROR | Forgot `error(ex)`, handler didn't record error, or different policy | Check Observation lifecycle and status mapper |
| ERROR span exists in SDK, missing in backend | Exporter, Collector, filter, retention, or ingestion failure | Check exporter/Collector telemetry |
| Some spans have exception events, lack status ERROR | Event recorded without setting status per policy | Cross-check API and tracing bridge |
| Parent and child appear as two separate traces | Lost or missing context inject/extract | Check headers and current span |
| Span is unusually short | Stopped/ended too early in async flow | Measure until actual work completes |
| Logs lack traceId/spanId | MDC/pattern unconfigured or context lost across thread switch | Check logging correlation and propagation |

**Head sampling** normally decides early, before the entire request finishes. Hence **you cannot assume a span turning `ERROR` will automatically be kept** if the trace was initially unsampled. Collector tail sampling can weigh status/errors after receiving spans, yet carries resource limits, timing constraints, and configuration dependencies.

Never set production sampling probability to 100% just to hunt down one bug. When investigating, use a reproduction environment, bounded observation windows, or an intentionally designed sampling policy; combine metrics/logs so overall error rates are never missed.

## 14. Asynchronous Handling: Errors Occurring After a Method Returns

In synchronous code, wrapping an operation in `try/catch/finally` suffices to report errors and stop Observation. In asynchronous code, this pitfall can happen:

~~~java
Observation observation = Observation.createNotStarted(
        "inventory.reserve.async", registry).start();

try {
    return executor.submit(() -> reserveInventory());
} finally {
    observation.stop(); // Too early if measuring until the task actually finishes.
}
~~~

This pattern stops the Observation right after submitting, not when `reserveInventory()` finishes. Exceptions thrown later on the worker thread are not reported to Observation as intended; the span may end before the error even happens.

An illustrative pattern with `CompletionStage`:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.concurrent.CompletionStage;
import java.util.function.Supplier;

public final class AsyncObservationMonitor {
    private final ObservationRegistry registry;

    public AsyncObservationMonitor(ObservationRegistry registry) {
        this.registry = registry;
    }

    public <T> CompletionStage<T> monitor(
            Supplier<CompletionStage<T>> submit) {

        Observation observation = Observation.createNotStarted(
                "inventory.reserve.async", registry).start();

        try {
            CompletionStage<T> stage = submit.get();
            return stage.whenComplete((result, error) -> {
                try {
                    if (error != null) {
                        observation.error(error);
                        observation.lowCardinalityKeyValue(
                                "outcome", "error");
                    } else {
                        observation.lowCardinalityKeyValue(
                                "outcome", "success");
                    }
                } finally {
                    observation.stop();
                }
            });
        } catch (RuntimeException | Error ex) {
            observation.error(ex);
            observation.stop();
            throw ex;
        }
    }
}
~~~

In this example, `error` in the callback may wrap the original exception (such as `CompletionException`). If the app classifies by root cause, unwrap safely and consistently. More importantly, the callback stops the observation only after the stage completes.

**Context propagation warning:** this snippet only demonstrates **error reporting and stop lifecycle**; it does **not automatically ensure the current observation/trace scope reaches the worker thread**. With executors or Reactor, you need proper context propagation (e.g., context snapshots or Spring's built-in support) for downstream spans to attach as valid children of the trace. Never open an `Observation.Scope` on thread A and try to close it on thread B.

## 15. Common Design Mistakes When Recording Span Errors

| Anti-Pattern | Why Is It a Problem? | Alternative |
| --- | --- | --- |
| Setting `status=ERROR` for all HTTP 4xx on the server | Many 4xx responses are valid per API contract | Follow semantic conventions; separate technical and business errors |
| Calling only `recordException` and assuming status is always `ERROR` | Exception event and span status are separate fields | Explicitly set status when using the OTel API directly and needing ERROR |
| Calling only `log.error(...)` expecting an exception event on the span | Logging and tracing are separate pipelines | Notify Observation or instrument the span properly |
| Setting `outcome=error` without notifying Observation of the exception | Metrics classify it, but trace lacks error semantics | Call `observation.error(ex)` for applicable technical errors |
| Calling `error(ex)` without `stop()` | Span/Timer may never finish cleanly | Always stop at the right boundary via `finally`/callback |
| Unconditionally recording error on parent and every child | Creates noise and double-counts failures | Mark each operation according to its own semantics |
| Putting exception messages, URLs with IDs, or userId in metric labels | High cardinality, data leakage risk | Use low-cardinality outcome/type; keep details in appropriate logs/traces |
| Wrapping an already auto-instrumented HTTP request in a manual span | Creates duplicate spans, confuses waterfalls | Keep built-in instrumentation; add custom spans only for new business steps |
| Stopping observation before async callback reports error | Fails to reflect true duration and errors | Stop when work actually completes |
| Treating missing traces as "no errors occurred" | Sampling/exporters may drop traces | Cross-check metrics, logs, and pipeline health |
| Treating HTTP 200 as "no downstream errors" | Fallbacks/retries can mask internal failures | Inspect child spans and downstream metrics |

If the system defines a custom `ObservationHandler`, ensure `supportsContext` selects the exact context type and avoid registering the same handler twice in the registry. Two tracing handlers performing the same job on one observation can produce duplicate spans or error events—which is completely different from two real retries.

## 16. Investigation Scenario: Inventory Timeout Slows Down Checkout

**Context.** After changing HTTP client configuration, `order-api` p95 latency jumps from 180 ms to 950 ms; HTTP 5xx rises only slightly, yet logs show many timeouts to `inventory-api`.

### Step 1 — Narrow Scope with Metrics

On dashboards, filter by route `POST /api/orders`, instance, response status, and the timeframe when errors started. Check RPS, error rate, p95 latency, and any business metric tracking `outcome=success/fallback/error` if instrumented.

Do not assume from a 1% HTTP 5xx rate that only 1% of inventory calls failed: fallbacks can return 200 for many requests.

### Step 2 — Inspect Sampled Traces

A trace might look like:

~~~text
POST /api/orders (SERVER)      820 ms  UNSET    response=200
  orders.create (INTERNAL)     800 ms  UNSET    outcome=fallback
    inventory.reserve (CLIENT) 700 ms  ERROR    timeout
    orders.fallback (INTERNAL)  40 ms  UNSET
~~~

Child span `inventory.reserve` has status `ERROR` even though the parent returned success. Inspecting the exception event may reveal `TimeoutException`. Still, **it is not guaranteed that the inventory server processed the request and returned an error**: the timeout might have occurred before connecting, while waiting for a response, or on the network. Cross-check client logs, trace propagation, and inventory-side metrics.

### Step 3 — Check Tracing API and Instrumentation

- Is the HTTP client configured/instrumented by Spring Boot properly?
- Does the client span carry safe method, URL route/peer info, and status/exception?
- When the error is caught and falls back, does client instrumentation report the error before recovery?
- Is another manual Observation wrapping the exact same HTTP client call and causing duplicate spans?
- Did trace context propagate to `inventory-api` via headers when requests actually reached the server?
- Did sampling/exporters drop some traces? Rely on metrics for the overall error rate.

### Step 4 — Remediate and Verify

Tune timeouts, connection pools, or retry logic based on verified causes. Then monitor:

- Did the HTTP client timeout rate drop?
- Did checkout p95 latency improve?
- Did fallback and 5xx counts return to acceptable thresholds?
- Do sample traces still show abnormal `ERROR` child spans?
- Do logs share trace IDs with accurate events and zero token or sensitive data leaks?

**Lesson:** span errors tell you **which operation** failed and where along the path; actual error rates must be quantified with metrics. A single trace does not prove system-wide impact.

## 17. Practice and Self-Check Questions

### Exercise A — Classifying Status

For the following scenarios, decide whether the corresponding span should typically be `ERROR`, `UNSET`, or depends on contract:

1. HTTP server returns 200 when a payment call succeeds.
2. HTTP server returns 404 for a nonexistent resource as an expected outcome.
3. HTTP client hits `SocketTimeoutException`.
4. A business step detects a valid payment decline.
5. A child span calling downstream fails, yet the parent completes fallback successfully.
6. An exception is caught and retried successfully inside one operation.

**Hint:** do not apply one code across the whole trace; evaluate span kind, work boundaries, and failure semantics. `UNSET` can be valid when an operation finishes normally without explicitly setting `OK`.

### Exercise B — Instrumenting with Micrometer Observation

Create an `InventoryService` with method `reserve(...)`:

- Use the Spring Boot-injected `ObservationRegistry`.
- Create observation `inventory.reserve` and attach a low-cardinality `channel`.
- On success, attach `outcome=success`.
- On timeout, attach `outcome=error`, call `observation.error(ex)`, and rethrow.
- Close scope and call `stop()` on all execution paths.
- Explain why order ID must not become a metric tag.

### Exercise C — Distinguishing Events and Status

In a direct OpenTelemetry snippet, perform both `span.recordException(ex)` and `span.setStatus(StatusCode.ERROR, "dependency failed")`. Then explain the independent value of each call; never assume `recordException` always sets status.

### Exercise D — Configuring and Verifying Traces

In a test environment with an active tracing bridge/exporter:

1. Trigger one successful request and one technical-error request.
2. Locate both traces in the backend when sampling allows.
3. Inspect span name, span kind, status, exception events, and duration.
4. Check whether `traceId/spanId` appear in logs when logging correlation is configured.
5. Compare the HTTP server span with client/downstream spans; explain when their statuses differ.
6. Lower sampling in the test environment and explain why some traces disappear while metrics keep counting requests.

### Exercise E — Catching Async Errors

A method creates an Observation, submits a `CompletableFuture`, and immediately calls `observation.stop()`. Refactor it so error recording and `stop()` occur when the future completes. Explain what context propagation must be added when the callback runs on another thread.

### Self-Check Questions

1. Is `UNSET` in OpenTelemetry an error? Does it mean the span never finished?
2. How does span status `ERROR` differ from an exception event?
3. In Micrometer, does `observation.error(ex)` automatically write an `ERROR` log line?
4. Why can a parent span remain non-error even when a child span is `ERROR`?
5. Why shouldn't every HTTP 4xx on a server be treated as an infrastructure error by default?
6. If an `ERROR` span is missing from the backend, where should you inspect sampling/exporters?
7. Why shouldn't exception messages or individual IDs be metric labels?
8. When a retry fails and the next attempt succeeds, does the error span count equal the failed request count?
9. When should an error be marked on the client span vs. the server span?
10. When an error occurs after a Future returns, why is `finally { observation.stop(); }` inside the submitting method too early?

**Completion criteria:** accurately describe status codes, distinguish span error from exception events and outcomes; instrument a technical error using Observation with proper lifecycle cleanup; understand HTTP/server/client semantics, propagation, sampling, and exporters; use metrics/logs to quantify span error impact while handling metadata safely.

## 18. Key Takeaways

- **Span status** reflects the conclusion about **a single operation**. `UNSET` is typically the default; `ERROR` indicates the operation failed; `OK` is explicit success.
- **Exception events do not replace status.** When using the OpenTelemetry API directly and needing both, record the exception event and set `ERROR` deliberately.
- In Micrometer, call `observation.error(ex)` to notify handlers of failures, and **always stop the observation** when the actual work finishes.
- Expected business rejections may belong under `outcome=declined` instead of marking every span `ERROR`. Keep rules consistent and separate from HTTP 5xx definitions.
- **A failing child span does not automatically fail its parent span.** Analyze the waterfall, retries, fallbacks, and trace context before concluding root cause.
- Metrics measure error rates and overall impact; logs describe events; traces pinpoint the failing step. Sampling/exporters/propagation can keep a trace from appearing.
- Keep metadata safe: metric tags must be low cardinality; never write tokens, sensitive payloads, or arbitrary exception messages into metric labels.
- For async tasks, propagate context and record error/stop inside the completion callback; never stop the span right after submission.

## References

- [Micrometer Reference — Observation introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer Reference — Observation components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [OpenTelemetry Specification — Traces API](https://opentelemetry.io/docs/specs/otel/trace/api/)
- [OpenTelemetry Specification — HTTP spans semantic conventions](https://opentelemetry.io/docs/specs/semconv/http/http-spans/)
- [OpenTelemetry Java — Record exceptions](https://opentelemetry.io/docs/languages/java/api/#record-exceptions)
