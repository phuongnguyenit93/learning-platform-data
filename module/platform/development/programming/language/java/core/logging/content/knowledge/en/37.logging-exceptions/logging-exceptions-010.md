# Reconciling Exceptions with Metrics in Java Core Logging

## 1. The Problem: Why Does the Number of Exceptions in Logs Differ from Errors on Dashboards?

In a Java application, an **exception**, a **log event**, a **metric measurement**, and a **trace/span event** are related, but they are not the same unit of measurement. An HTTP request may throw an exception multiple times, be retried, and then return successfully. Conversely, a request may return 400 due to a validation failure without throwing any exception at all. Therefore, the question "why are there 300 ERROR logs but only 80 failed requests?" cannot be answered simply by counting log lines.

To reconcile them accurately, you must determine:

1. **What is being counted:** an attempt, a downstream call, a business operation, an HTTP request, or a background job.
2. **Recording point:** when the exception is caught, when a retry starts, when the request completes, or when the exporter receives the event.
3. **Outcome:** transient failure followed by recovery, final failure, cancellation, validation rejection, or service degradation.
4. **Time and scope:** service, environment, operation, route, time window, clocks, and ingest delay.
5. **Observation conditions:** level filtering, sampling, duplicate logs, async queues, metric scrapes/exports, and collector errors.

For example: `POST /api/payments` calls a payment provider. The first attempt throws `SocketTimeoutException`, and the retry succeeds. A WARN log and a `dependency.exceptions` metric may appear, while the `http.requests.failed` metric must be **0 for this request** if the final HTTP result succeeds. Having both numbers differ is semantically correct.

A core principle: **logs explain what happened; metrics show frequency, distribution, and impact; traces connect the steps of a processing flow.** Do not force the number of log lines, `Throwable` instances, and failed requests to be equal.

## 2. Counts That Must Be Distinguished

| Quantity | Unit | Recording Time |
| --- | --- | --- |
| `requests_total` | Logical request of the service at an entry point | Once when the request is recorded according to the defined lifecycle |
| `requests_failed_total` | Request ending with an outcome defined as a failure | Once **when the final outcome is determined** |
| `exception_attempts_total` | Exception observed at the boundary of an attempt | Each time an attempt fails, even if it later recovers |
| `retries_total` | Actual retry started | Does not count the initial attempt |
| `recovered_requests_total` | Request that failed at least one attempt but ultimately succeeded | Once at completion |
| `fallbacks_total` | Fallback execution according to the contract | When the fallback is actually executed |
| `http_request_duration` | Duration observation for the request | When the request completes, measured over the proper lifecycle |
| Exception log | A log event about an error | According to logger/backend policy and severity level |
| Span exception event | Error data attached to a span | According to instrumentation/tracing sampling |

These metric names are **illustrative**, not default names from the JDK, Micrometer, OpenTelemetry, or Prometheus. Frameworks may emit HTTP metrics under different names and units; you must check the actual contract.

Distinguishing three levels of failure is critical:

- **Attempt failure:** a single call to a DB/downstream service or a single retry step fails.
- **Operation failure:** the business logic or job logic fails after retry/fallback mechanisms.
- **HTTP request failure:** the final response matches the HTTP error definition, typically distinguishing clearly between 4xx and 5xx.

For example, a request with 3 failed downstream calls followed by a successful fallback may have 3 attempt failures, 1 fallback, and 0 failed HTTP requests. If you use the same name `errors_total` for all three layers, the dashboard will be impossible to interpret correctly.

## 3. One Request, Multiple Attempts, and Multiple Logs

```text
HTTP request req-42
      |
      +-- attempt 1 -> IOException/timeout
      |      +-- WARN log "dependency.attempt.failed"
      |      +-- exception_attempts_total += 1
      |      +-- retries_total += 1
      |
      +-- attempt 2 -> success
             |
             +-- requests_total += 1
             +-- requests_failed_total += 0
             +-- recovered_requests_total += 1
```

The same request ID can appear in multiple log events: request started, downstream timeout, retry scheduled, request completed. **Not every event is a request.** If a collector retries exporting the same timeout log event, **two copies** of a single log event may even appear.

When defining an error rate metric, use the same unit type and the same owner:

```text
request_error_rate =
    increase(requests_failed_total within window)
    / increase(requests_total within window)

dependency_attempt_failure_rate =
    failed_dependency_attempts
    / all_dependency_attempts
```

These two ratios answer two different questions. A service can have a high dependency attempt failure rate yet a low HTTP error rate thanks to retries and fallbacks; that is a **degraded dependency** that needs separate monitoring because retries increase latency and resource consumption.

## 4. Reconciliation Matrix for Common Scenarios

| Scenario | Java Exception | Expected Log | Appropriate Metric |
| --- | --- | --- | --- |
| Request succeeds immediately | None | Completion log per policy | requests +1, failed +0 |
| Attempt 1 times out, attempt 2 succeeds | One exception | WARN for failed attempt with `outcome=RETRY` | attempt exception +1, retry +1, recovered +1, failed +0 |
| Both attempts fail, returns 503 | Two exceptions | WARN for attempt 1, final error with outcome FAILED | attempt exception +2, retry +1, failed request +1 |
| Validation 400 handled normally | Possibly none | Request completion status 400, reason code | HTTP 4xx +1; exception +0 |
| Exception caught, fallback returns 200 | Exception present | WARN/INFO clearly noting recovered/degraded | fallback +1, failed request +0 |
| Unhandled exception, container returns 500 | Exception present | ERROR at exception boundary | failed request +1; exception count depends on owner |
| Background job fails after HTTP 202 | Present in worker | Job exception log | job failed +1, does not retroactively change HTTP 202 |
| A Throwable is wrapped and rethrown across layers | Possibly multiple Throwable objects | Avoid logging duplicate stack traces at every layer | Count attempt/operation at the boundary, not per catch |
| A log event is re-sent by the exporter | No new business exception | Possibly 2 copies with the same event ID | Do not increment the business failure counter again |
| Stream disconnected by client | Possibly `IOException` | Distinguish client disconnect from server failure | Separate outcome per contract |

An exception is only a **Java language mechanism**. The HTTP or business outcome is a decision of the service. If a `ControllerAdvice` converts an exception into HTTP 409, the metric status must still reflect 409—do not assume every exception equals 5xx.

## 5. Designing Exception Logs Traceable from Metrics

Example structured log for an error at an attempt boundary:

```json
{
  "timestamp": "2026-01-01T00:00:00Z",
  "event.name": "dependency.attempt.failed",
  "service.name": "checkout-api",
  "deployment.environment.name": "prod",
  "operation": "payment.authorize",
  "http.route": "/api/payments",
  "request_id": "req-42",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "attempt": 1,
  "exception.type": "java.net.SocketTimeoutException",
  "error.code": "DOWNSTREAM_TIMEOUT",
  "outcome": "RETRY",
  "message": "Payment provider timed out"
}
```

This is an **illustrative** schema, not a default format automatically understood by every cloud backend, Micrometer, or OpenTelemetry. To query by fields, you must have a JSON encoder/parser and corresponding mapping rules.

Key fields:

1. **`event.name`** has a stable meaning, distinguishing attempt failures from request completion.
2. **`operation` and `http.route`** allow filtering within the same metric scope, typically from a bounded set of values.
3. **`error.code` and `exception.type`** define error categories that can be normalized as metric dimensions.
4. **`attempt`, `outcome`** indicate whether the event is merely a retry or a final failure.
5. **`request_id` and `trace_id`** correlate logs within a request or trace, and are **not** used as metric labels.
6. **Timestamp/UTC** for comparing time windows, while also knowing the ingest timestamp if the pipeline is delayed.
7. **Message/stack trace** for investigation; must be sanitized, size-limited, and protected against sensitive data leaks.

An HTTP completion log should have `event.name=http.request.completed`, final status, duration, and the outcome of the entire request. Do not set `outcome=FAILED` on the completion event just because the first attempt threw an exception; base it on the final response.

### Log Levels and Stack Trace Policy

A timeout that will be retried is usually more appropriate as WARN at the attempt boundary rather than an ERROR request failure. You can keep short summaries for attempts and only log the full stack trace when needed at the final boundary to reduce duplicate log volume.

If the same `Throwable` is logged at the DAO, service, and controller layers and then rethrown, three ERROR logs can come from **one failed request**, not three failed requests. Use the event name and log owner to distinguish them; do not rely on two stack traces looking identical for business deduplication.

## 6. Complete Java 17 Example with Deterministic Stdout

This example uses **only JDK 17**. Three requests are processed sequentially. The counters in the example are static integers for readability, not a thread-safe implementation for production Servlets. Logging uses JUL (`java.util.logging`) with a Handler writing fixed messages to stdout, without adding timestamps from the default formatter.

Scenario:

- `req-1` succeeds immediately.
- `req-2` encounters `IllegalStateException` on attempt 1, then succeeds on retry.
- `req-3` encounters an exception on both attempt 1 and attempt 2; after attempt 2 the request fails finally.

Save as **`ExceptionMetricReconciliationDemo.java`**:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ExceptionMetricReconciliationDemo {
    private static final Logger LOG =
            Logger.getLogger("example.exception.metrics");

    private static long requestsTotal;
    private static long requestsFailed;
    private static long exceptionAttempts;
    private static long retries;
    private static long requestsRecovered;

    private static void executeAttempt(String requestId, int attempt) {
        if ("req-2".equals(requestId) && attempt == 1) {
            throw new IllegalStateException("temporary downstream failure");
        }
        if ("req-3".equals(requestId)) {
            throw new IllegalStateException("downstream unavailable");
        }
    }

    private static boolean handleRequest(String requestId) {
        requestsTotal++;

        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                executeAttempt(requestId, attempt);

                if (attempt > 1) {
                    requestsRecovered++;
                }
                return true;
            } catch (IllegalStateException ex) {
                exceptionAttempts++;

                boolean willRetry = attempt < 2;
                String outcome = willRetry ? "RETRY" : "FAILED";
                Level level = willRetry ? Level.WARNING : Level.SEVERE;

                LOG.log(level,
                        "request_id=" + requestId
                        + " attempt=" + attempt
                        + " exception_type="
                        + ex.getClass().getSimpleName()
                        + " outcome=" + outcome);

                if (willRetry) {
                    retries++;
                } else {
                    requestsFailed++;
                    return false;
                }
            }
        }
        throw new AssertionError("Unreachable");
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        Handler sink = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(
                            record.getLevel().getName() + " "
                            + record.getMessage());
                }
            }

            @Override
            public void flush() {}

            @Override
            public void close() {}
        };
        sink.setLevel(Level.ALL);
        LOG.addHandler(sink);

        try {
            handleRequest("req-1");
            handleRequest("req-2");
            handleRequest("req-3");

            System.out.printf(
                    "METRIC requests_total=%d requests_failed_total=%d "
                    + "exception_attempts_total=%d retries_total=%d "
                    + "requests_recovered_total=%d%n",
                    requestsTotal, requestsFailed, exceptionAttempts,
                    retries, requestsRecovered);
        } finally {
            LOG.removeHandler(sink);
            sink.close();
        }
    }
}
```

Compile/run commands:

```bash
javac ExceptionMetricReconciliationDemo.java
java ExceptionMetricReconciliationDemo
```

**Exact stdout:**

```text
WARNING request_id=req-2 attempt=1 exception_type=IllegalStateException outcome=RETRY
WARNING request_id=req-3 attempt=1 exception_type=IllegalStateException outcome=RETRY
SEVERE request_id=req-3 attempt=2 exception_type=IllegalStateException outcome=FAILED
METRIC requests_total=3 requests_failed_total=1 exception_attempts_total=3 retries_total=2 requests_recovered_total=1
```

Reconciling each number:

| Counter | Value | Reason |
| --- | ---: | --- |
| `requests_total` | 3 | Three logical requests, each accepted once |
| `requests_failed_total` | 1 | Only `req-3` failed finally |
| `exception_attempts_total` | 3 | `req-2` had one attempt exception; `req-3` had two |
| `retries_total` | 2 | Both `req-2` and `req-3` tried a second time |
| `requests_recovered_total` | 1 | Only `req-2` recovered after retry |
| Exception log events | 3 | Each failed attempt logged one event at the chosen boundary |

**Limitations:** the program uses non-thread-safe static `long` fields and a text-printing Handler, does not export metrics, has no HTTP server, and does not log actual stack traces or trace links. In production, use a metric registry/thread-safe counters and an appropriate logging encoder/handler. This is a test of **counting semantics**, not a performance benchmark or durability contract.

The example does not print the exception message so that stdout remains deterministic and avoids unsafe data. In a real application, when investigation is needed, use the logging overload that accepts `Throwable` at the chosen boundary, such as `logger.log(Level.SEVERE, "Request failed", ex)`. Do not re-log the full stack trace at every layer if it adds no value.

## 7. Micrometer and Spring Boot: Where to Increment Counters

Micrometer supports `Counter`, `Timer`, `DistributionSummary`, and other measurement abstractions; Spring Boot can provide HTTP server observations/metrics when configured. Do not manually instrument an additional request counter that duplicates what the framework already produces and then sum the two sources, doubling the request count.

Example design catalog:

```text
dependency.attempt.exceptions
  tags: service, operation, error_code, exception_type

business.requests.failed
  tags: service, operation, outcome

business.operation.duration
  tags: service, operation, outcome
```

These are **illustrative application-chosen names**, not built-in to every Micrometer registry. Illustrative Java snippet (not standalone; requires `micrometer-core`, `MeterRegistry`, and context variables):

```java
Counter.builder("dependency.attempt.exceptions")
        .tag("operation", operationName)
        .tag("error_code", errorCode)
        .register(meterRegistry)
        .increment();
```

Place this counter increment **once at the defined attempt boundary**. For `requests_failed_total`, increment when the final outcome is failed at the corresponding HTTP/operation boundary. Avoid placing the same counter name in the repository, service, controller, and exception handler, which causes a single request to be counted multiple times.

When exported to Prometheus, Micrometer names may be normalized and suffixed according to the registry and naming conventions. Always check the exact actual metric name in the backend before writing queries. Do not assume that the `http.server.requests` metric in version A keeps the exact same name, tags, and units in version B.

### Timers and Histograms

Error counters only tell you how many times something happened, not the latency impact. A request with a successful retry can take much longer, so timers/histograms are equally important. Measure elapsed time using a monotonic clock across the request or operation lifecycle; do not use the difference between two wall-clock timestamps as a duration clock.

Example relationship:

```text
request succeeded after 2 attempts:
  failed_request_counter += 0
  attempt_exception_counter += 1
  retries_counter += 1
  duration histogram records full request time once
```

Do not measure only the last attempt and label it as the full request duration. In async/streaming HTTP, completion may occur later than when the controller returns; instrumentation must choose the right lifecycle.

## 8. OpenTelemetry and Correlating Logs, Metrics, and Traces

OpenTelemetry organizes telemetry around resource attributes, context, and distinct signal types. **There is not automatically one metric for every exception log.** Depending on instrumentation, an exception may become a span event, a logger record, or be omitted when filtered.

Reconciliation strategy:

- Logs carry `trace_id`, `span_id`, service, operation, error code, attempt, and outcome.
- Spans represent a call/operation; an exception event can be attached to the active span. Span status does not necessarily equal the final HTTP status in every workflow.
- Metrics aggregate by dimensions with bounded cardinality such as service, route, outcome, and error code.
- Exemplars, if supported by the backend/SDK, let you jump from a metric sample to a trace without turning trace IDs into labels on every time series.
- If trace sampling does not keep a specific trace, logs can still carry the ID and request metrics must still reflect traffic according to policy.

OTel semantic convention names for HTTP and exceptions change across versions; `error.type`, `exception.type`, or route attributes must be verified against the actual instrumentation. Some backends require specific mappings for the "View trace" button to work.

### MDC and Async Context

With SLF4J/Logback, MDC typically stores data per thread. When a request moves across an `ExecutorService`, `CompletableFuture`, or reactive pipeline, MDC does not automatically propagate accurately to worker threads. This can cause logs to miss or carry the wrong `request_id`/`trace_id` while metrics still increment accurately.

Use context propagation supported by the framework/instrumentation, restore/clear context when tasks finish, and test thread pool reuse. **MDC is observability context**, and should not be used as an authorization source or as a metric label containing arbitrary IDs.

## 9. Cardinality: Do Not Turn Log Details into Metric Labels

Logs can retain request IDs, stack traces, and messages for search; metric time series generally must have a **bounded set of labels**.

| Relatively Suitable Label | Example | Condition |
| --- | --- | --- |
| `service` | `checkout-api` | Managed service catalog |
| `environment` | `prod` | Small set |
| `operation` or `http.route` | `payment.authorize`, `/api/orders/{id}` | Route template rather than raw URL |
| `outcome` | `SUCCESS`, `FAILED`, `RECOVERED` | Small enum |
| `error_code` | `DOWNSTREAM_TIMEOUT`, `VALIDATION_ERROR` | Controlled catalog |
| `exception_type` | `SocketTimeoutException` | Limit class count, group if needed |
| `dependency` | `payment-provider` | Logical name, avoid dynamic hosts |

**Do not use** `request_id`, `trace_id`, order ID, user ID, exception message, stack trace, raw URL, SQL statement, or token as metric labels. A million IDs will cause extreme series cardinality; put IDs in access-controlled logs/traces instead of metrics.

Even exception types must be controlled: an application may have many custom error classes; do not use `exception.toString()` or the message as the type. For overly broad error groups, map them to categories like `TIMEOUT`, `CONFLICT`, `INVALID_INPUT`, `UNKNOWN`.

## 10. Legitimate Causes of Discrepancies

### A. Retries and Fallbacks

A request may throw multiple exceptions, be retried, and then succeed. Having the final failure metric lower than the attempt exception count is correct. Even when a circuit breaker is open and returns a fallback, a request may degrade without throwing the same new exception type.

### B. Exceptions Caught, Wrapped, or Rethrown

A low-level error may be wrapped into a `ServiceException` and rethrown through multiple layers. If every `catch` logs a stack trace and increments a counter, the system measures one error multiple times. Separate dependency attempt metrics from final operation metrics. Prefer logging fully at a single boundary with consistent context, and emit distinct event types only when genuinely needed.

### C. HTTP/Business Outcomes Not Matching Exceptions

A 400 validation error or access denial may be a normal logic branch. Conversely, an HTTP 200 may carry a business outcome `FAILED` in its body if the API is designed that way. Do not use exception metrics as a substitute for HTTP 5xx metrics or business failure metrics.

### D. Async Jobs After the HTTP Request Ends

If an endpoint returns 202 Accepted and the worker later fails, the job failure does not turn the HTTP 202 response into a 500. The job's logs/metrics must have an appropriate job ID/correlation and a separate job outcome unit.

### E. Log Level/Sampling and Queue Drops

An exception may be observed in code, yet its log may be dropped by level filtering, sampling, async queue discard, Collector parse errors, or backend quotas. Metrics may still be updated. Conversely, metrics may be lost during scrape/export while logs remain complete.

### F. Event Time, Ingestion Time, and Metric Windows

A log occurs at 10:00:58 but is ingested into the backend at 10:01:14. Counters are exported/scraped at different times. If you compare charts across exact 1-minute windows without allowing tolerance and accounting for ingest lag, the numbers can diverge.

### G. Counter Resets and Aggregation

A process restart resets in-memory counters to 0. Time-series systems typically handle counter resets in `rate()`/`increase()` properly; do not take the raw difference between two points before and after a restart and conclude there is a negative error count. When aggregating across multiple instances, preserve the proper service, route, environment, and group labels.

### H. Multiple Services Observing the Same Incident

A gateway, a service, and a downstream service may all log and measure the same failure. The sum of "errors" across all services is not the number of failed user requests. Measurement boundaries must be chosen clearly: edge request, per-service request, dependency attempt, or business operation.

## 11. Reconciliation Procedure When a Dashboard Shows a Spike

1. **Check the metric name and definition:** Is it counting failed requests, error responses, or attempts? Which instrumentation owner emits it?
2. **Select the scope:** service, environment, operation/route, outcome, and time range; check clocks, timezones, and ingest lag.
3. **Compute ratios with matching units:** only two counters with the same scope may be used as numerator/denominator for an error rate.
4. **Find corresponding logs:** filter by service, operation, `event.name`, error code; distinguish `dependency.attempt.failed` from `http.request.completed`.
5. **Grab correlation IDs:** use the `request_id`/`trace_id` of a representative request; reconstruct the retry/fallback/exception-handler timeline.
6. **Identify counter increment points:** are there logs from multiple layers while the metric increments once, or is a single counter incremented redundantly across multiple `catch` blocks?
7. **Check sampling and missing data:** were logs filtered/dropped, or did metrics experience scrape errors or stale series?
8. **Check timing:** logs may arrive after the scrape window; query with an appropriate delay tolerance.
9. **Verify the final outcome:** did the request actually fail or recover, and was it an HTTP error or a business error?
10. **Document findings and fix at the right layer:** schema, instrumentation, filters, exporter pipeline, or dashboard query.

Conceptual query example:

```text
Metric:
  increase(requests_failed_total{service="checkout-api"}[5m])

Log:
  filter service.name="checkout-api"
     and event.name="http.request.completed"
     and outcome="FAILED"
     and timestamp in comparable window

Trace:
  inspect trace_id from representative failed request
```

This is **not a query that can be copied verbatim into every backend**. In Prometheus, `increase(counter[5m])` must be grouped by the right labels and handle resets; in Cloud Logging, Elastic/Loki, or other systems, filter syntax and schemas differ.

## 12. Calculating Error Rate Correctly — and Incorrectly

Incorrect approach:

```text
ERROR logs in 5 minutes = 150
HTTP requests in 5 minutes = 1000

150 / 1000 = 15% failed HTTP requests? CANNOT BE CONCLUDED.
```

The 150 logs may include retries, background job errors, duplicate stack traces, exporter duplicates, or recovered exceptions; meanwhile, some failed requests produce no ERROR log.

Correct approach when both metrics share the same boundary and policy:

```text
requests_total increase over 5 minutes = 1000
requests_failed_total increase over 5 minutes = 20

request_error_rate = 20 / 1000 = 2%
```

Here `requests_failed_total` is defined as **requests that ended in failure** according to the contract. If you need a 5xx rate, use final HTTP status 5xx; if you want business failures, use a separate counter. When the denominator is 0, handle the chart/query according to defined rules instead of dividing by 0.

Do not conclude that 20 failed requests must produce exactly 20 ERROR logs: completion events may follow a different policy, retries produce extra attempt logs, or stack traces may only be logged for a subset.

## 13. A Shared "Observability Contract"

| Field | In Logs | In Metrics | In Traces |
| --- | --- | --- | --- |
| `service.name`, environment | Yes | Bounded tag/resource | Resource |
| `operation`/`http.route` | Yes | Bounded label | Span name/attribute |
| `outcome`, `error_code` | Yes | Enum tag | Span attribute/appropriate status |
| `exception.type` | Yes when error occurs | Controlled tag | Exception event when instrumented |
| `request_id` | Yes for event lookup | **No** label | Optional correlation attribute |
| `trace_id`/`span_id` | Yes if context exists | **No** label; exemplar if supported | Trace/span identifier |
| `attempt` and retry result | Yes | Count retries, no request ID label | Subspan/attempt event |
| Exception message/stack | Yes when needed, sanitized | **No** tag | Must protect sensitive data |
| Duration | Completion log | Timer/histogram | Span duration |

Lock down conventions: event names, metric names, owner of each counter, error code list, status mapping, request/attempt structure, timestamps, label limits, and retention. Manage schemas/versions as applications and backends upgrade.

The contract must distinguish **cause** (dependency timeout) from **final impact** (request success/failure). When complete, metrics show overall health while logs/traces provide concrete evidence.

## 14. Testing and Monitoring Both Pipelines

### Recommended Tests

| Scenario | Expected Log | Expected Metric |
| --- | --- | --- |
| Immediate success | No attempt exception | request +1, failed +0 |
| Timeout then retry succeeds | WARN attempt=1, outcome=RETRY | exception attempt +1, retry +1, recovered +1 |
| Both attempts fail | WARN attempt=1, final ERROR/SEVERE | attempt +2, retry +1, failed request +1 |
| Business validation returns 400 | Completion has status/reason | HTTP 4xx +1, exception not required |
| Catch exception and fallback | Shows recovered indicator | failure +0, fallback/degraded per contract |
| Wrap/rethrow | No duplicate same stack across layers | Request final failure increments once |
| Background job fails | Log belongs to job | Job error +1; already-returned HTTP unchanged |
| Thread pool/reactive context | Request ID accurate, not mixed across threads | Bounded labels, accurate counts |
| Log queue full | Pipeline drop/retry metrics present | Business counters still reflect business state |
| Metrics exporter fails | Logs may still be complete | Scrape/export health reports error |
| Process restart | Logs may arrive late | Counter reset query shows no anomalous negatives |
| Message contains secret | Redaction works | No tags containing secrets |
| Multi-service request | Events distinguish service/span | Do not confuse edge errors with dependency errors |

For unit tests, use stubs/fakes for downstream dependencies to force errors on specific attempts, and assert counter increments and log sink output. For integration tests, run a real backend/metric registry/collector, and verify ingestion and eventual queries using a wait-with-timeout condition instead of `Thread.sleep(1000)` and assuming completion.

### Health of Logging and Metric Pipelines

- Logging: dropped events, async queue depth, exporter errors, parse failures, ingest lag, and missing heartbeats.
- Metrics: scrape target up/down, remote-write backpressure, export failures, stale series, label cardinality, and resets.
- Tracing: sampling rate, missing spans, exporter errors, context propagation.
- Business: request/transaction counts from a trusted boundary, used for independent reconciliation when the observability pipeline fails.

If metrics show request traffic is still flowing while the log rate is 0, the log level/sampling may have changed or the pipeline may have lost signal. If logs show errors but metrics show none, the metrics exporter may be failing or instrumentation may be missing. Never automatically treat "no samples" as "0 errors."

## 15. Common Mistakes and How to Fix Them

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Using `count(ERROR logs)` to count failed requests | Duplicates, retries, sampling skew the count | Use the final request failure metric |
| Incrementing failed requests at every `catch` | One request counted multiple times | Single owner at the completion boundary |
| Logging full stack then rethrowing across layers | Duplicate logs, higher cost | Log stack at a boundary with context |
| Confusing attempt exceptions with final errors | Successful retries still marked as failed | Separate attempt/recovered/failed |
| Using exception message as a metric label | High cardinality and PII exposure | Use normalized error codes/types |
| Attaching trace ID or request ID as a metric label | Creates unbounded time series | Keep IDs in logs/traces; use exemplars if supported |
| Calling HTTP 400 a 5xx because an exception occurred | Wrong response status semantics | Map according to final HTTP status |
| Async job fails and increments HTTP 500 after 202 returned | Rewrites request history retroactively | Use a separate job outcome metric |
| Comparing this minute's log ingest with another minute's metric scrape | Mismatch due to lag | Align windows + ingest delay |
| Summing errors from gateway, service, and dependency | Double counting the same failure | Distinguish measurement boundaries |
| Assuming metric/log export is always complete | Lost samples due to pipeline failures | Self-metrics, canaries, health alerts |

## 16. Implementation Checklist for Java Applications

- [ ] Are there separate definitions for request, operation, attempt, retry, and exception occurrence?
- [ ] Does each counter have a single clear owner and increment point, without incrementing the same metric across multiple layers?
- [ ] Are failed attempts where the request recovered distinguished from requests that actually failed?
- [ ] Do logs include service, operation/route, error code, attempt/outcome, and necessary correlation IDs?
- [ ] Are duplicate `Throwable` logs avoided when wrapping/rethrowing, and unnecessary stack traces limited?
- [ ] Are exception messages/stack traces protected against secrets, tokens, and personal data?
- [ ] Are metric tags limited to bounded enums/routes/services, with no dynamic IDs or messages?
- [ ] Are built-in framework/HTTP metrics understood before adding custom counters?
- [ ] Is context from SLF4J MDC/OTel properly propagated and cleaned up across threads/reactive flows?
- [ ] Do dashboards use matching windows, timezones, counter reset handling, and multi-instance scope?
- [ ] Are success, retry-recovered, final failure, validation 4xx, async job, and exporter failure scenarios tested?
- [ ] Is there self-monitoring for the log pipeline, metric pipeline, and tracing pipeline when reconciliation data diverges?

**Remember:** an **exception** is an event in the execution flow, a **log** is detailed evidence governed by logging policy, and a **metric** is an aggregated measurement at a clear boundary. To reconcile them accurately, distinguish attempts from requests, define final outcomes, share common error codes/services/operations, keep request/trace IDs in logs rather than metric labels, and check both sampling and pipeline health. Two numbers differing is often meaningful information — not necessarily a bug.
