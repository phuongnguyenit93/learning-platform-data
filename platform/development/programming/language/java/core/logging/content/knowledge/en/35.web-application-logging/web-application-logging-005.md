# Request Duration in Java Web Logging

## 1. What Is Request Duration?

**Request duration** is the amount of time the system records to process an HTTP request, measured from a **clearly defined start point** to a **clearly defined end point**. For example, a Java service receives `GET /api/orders/42`, performs authentication, queries the database, builds the response, and returns HTTP 200. If the time from the beginning to the end of the measured scope is 127.4 ms, a summary log might look like:

```text
2026-11-10T10:15:20.123Z INFO event=http.request.completed method=GET route=/api/orders/{id} status=200 duration_ms=127.400 trace_id=4bf92f3577b34da6a3ce929d0e0e4736
```

Here, `duration_ms` is the **length of a time interval**, not a timestamp. A line like `duration_ms=127.400` only makes sense when you know the **start point, end point, and instrumentation scope**. For example, a filter inside the application might not include the TLS connection time at the load balancer or the time it takes the client to download the full response body.

Within **Web Application Logging**, measuring request duration helps:
- Detect slow endpoints or sudden latency spikes.
- Correlate fast/slow requests with HTTP status, trace, service, version, and pod.
- Investigate timeout, retry, or error requests.
- Track time spent in authentication, controllers, downstream HTTP calls, databases, and queues.
- Verify the impact of new releases or configuration changes on user experience.

**You should not rely solely on a single request's log to draw conclusions about system performance.** Logs are great for investigating individual requests, while metrics for latency distribution, p95/p99, and throughput are usually better suited for monitoring overall traffic.

## 2. A Request Has Multiple Different "Processing Times"

```text
Client          Proxy/Load balancer        Java Server            Database
  |---- DNS/TCP/TLS ---->|
  |---- request bytes -->|---- forward ---->|
  |                      |                   |-- auth/filter -----|
  |                      |                   |-- controller ------|
  |                      |                   |-- DB query ----------------->|
  |                      |                   |<--------- result ------------|
  |                      |                   |-- serialize/write |
  |<--- response bytes --|<---- response ----|
```

There are at least four measurement scopes to distinguish:

| Duration Type | Start point → End point | What is included / excluded |
| --- | --- | --- |
| **Client-perceived latency** | Client starts the call → client receives the expected result | May include DNS, connect, TLS, network, redirects, download, retries; depends on how the client measures |
| **Proxy/edge duration** | Proxy starts receiving → proxy finishes processing per its definition | May include waiting on upstream and transferring the response; does not match server duration exactly |
| **HTTP server request duration** | Instrumentation start point in the server → corresponding end point | Usually includes part of filters/framework/controller/downstream; excludes client DNS/TLS |
| **Handler/controller duration** | Entering the handler method → method returns/finishes | Narrower than end-to-end request; may exclude auth, filters, serialization, or async completion |

For example, the following measurements **can all be simultaneously true**:

```text
client_e2e_ms=450.0
proxy_ms=370.0
server_request_ms=325.0
controller_ms=280.0
database_ms=210.0
```

Do not add them together: many intervals are **nested**, not sequential independent phases. Avoid assuming `server_request_ms + db_ms` equals the request duration—the DB call is already inside the request processing scope if it happens synchronously during the request.

**The first step when diagnosing "wrong duration": identify the exact segment the instrumentation is measuring.**

## 3. Units of Measurement and Why Timestamps Differ from Duration

The start time of an event can use `Instant.now()` to record a log timestamp. However, measuring **elapsed time** should use a monotonic clock such as `System.nanoTime()`:

```java
long startedAtNanos = System.nanoTime();
try {
    doWork();
} finally {
    long elapsedNanos = System.nanoTime() - startedAtNanos;
    double durationMs = elapsedNanos / 1_000_000.0;
    log.info("duration_ms={}", durationMs);
}
```

This is an **integration snippet inside an application that already has `log` and `doWork()`**, not a standalone Java program. `System.nanoTime()` is suitable for computing the difference between two readings within the same JVM process. Its absolute value has an arbitrary origin, **is not a Unix timestamp**, and must not be used to compare across two processes.

Why avoid `System.currentTimeMillis()` for measuring duration?

- The wall-clock can be adjusted by NTP, sometimes jumping forward or backward.
- Clock resolution and clock adjustment schedules can make short measurements unstable.
- A wall-clock timestamp is useful for locating an event on a timeline, **not as a replacement for a monotonic elapsed clock**.

Example of incorrect calculation:

```java
long start = System.currentTimeMillis();
// ... work happens ...
long duration = System.currentTimeMillis() - start;
```

When the system clock jumps backward, duration can become negative; when it jumps forward, duration can appear artificially inflated. Use `nanoTime` for measuring time intervals instead. Do not use `Instant.now().toEpochMilli()` as a monotonic clock.

### 3.1. Using the Right Units

| Value | Meaning | Conversion |
| --- | --- | --- |
| `ns` | Nanosecond | 1 ms = 1,000,000 ns |
| `µs` | Microsecond | 1 ms = 1,000 µs |
| `ms` | Millisecond | 1 s = 1,000 ms |
| `s` | Second | 1 s = 1,000,000,000 ns |

If the duration is `123_456_789 ns`:
- `TimeUnit.NANOSECONDS.toMillis(...)` returns **123 ms** (truncating the remainder).
- Dividing by `1_000_000.0` returns **123.456789 ms** (floating-point).
- `Duration.ofNanos(...).toMillis()` also returns **123 ms**.

Do not name a field `duration_ms` while logging nanoseconds. If you need very fine-grained analysis, keep an integer `duration_ns` or standardize according to your backend schema, and avoid mixing multiple units in the same field.

## 4. Standalone Java 17+ Example with Deterministic Output

The program below uses an **injected fake clock** to demonstrate the exact calculation without depending on machine speed. In production, replace the fake clock with `System::nanoTime`. The goal is to understand how to emit **one summary log when processing finishes**, even when the work throws an exception.

Save as `RequestDurationDemo.java`:

```java
import java.util.Locale;
import java.util.function.LongSupplier;

public class RequestDurationDemo {
    private static final class FakeNanoClock implements LongSupplier {
        private final long[] ticks = {
                1_000_000_000L, 1_023_450_000L,
                2_000_000_000L, 2_004_500_000L
        };
        private int index;

        @Override
        public long getAsLong() {
            return ticks[index++];
        }
    }

    private static void handle(String method,
                               String route,
                               int status,
                               LongSupplier clock,
                               Runnable work) {
        long startedAt = clock.getAsLong();
        try {
            work.run();
        } finally {
            long nanos = clock.getAsLong() - startedAt;
            double millis = nanos / 1_000_000.0;
            System.out.printf(Locale.ROOT,
                    "event=http.request method=%s route=%s "
                  + "status=%d duration_ms=%.3f%n",
                    method, route, status, millis);
        }
    }

    public static void main(String[] args) {
        LongSupplier clock = new FakeNanoClock();

        handle("GET", "/api/orders/{id}", 200, clock, () -> {});

        try {
            handle("POST", "/api/orders", 500, clock,
                    () -> { throw new IllegalStateException("simulated"); });
        } catch (IllegalStateException ex) {
            System.out.println("handled=IllegalStateException");
        }
    }
}
```

Run on JDK 17 or higher:

```bash
javac --release 17 RequestDurationDemo.java
java RequestDurationDemo
```

Exact stdout:

```text
event=http.request method=GET route=/api/orders/{id} status=200 duration_ms=23.450
event=http.request method=POST route=/api/orders status=500 duration_ms=4.500
handled=IllegalStateException
```

**Explanation:**
1. The first call reads 1,000,000,000 ns and 1,023,450,000 ns → difference is **23.45 ms**.
2. The second call reads 2,000,000,000 ns and 2,004,500,000 ns → difference is **4.5 ms**.
3. `finally` still logs the duration when the work throws an exception; afterwards, the exception propagates to `catch` in `main`.
4. In this demo program, `status` **is passed in** to test formatting; it does not infer a real HTTP status. A web filter must retrieve the status from the response/framework.
5. The fake clock makes the output deterministic, **not a benchmark**. In a real application, do not write to stdout manually like this; use an appropriate logger.

Note: never assume any `finally` block will run if the JVM is forcefully killed, loses power, or crashes at the native level. Also, because `finally` can log an error before the HTTP error handler decides the final status, you must understand the framework lifecycle.

## 5. Logging a Structured Request Summary

A good log record should have controlled fields:

```json
{
  "event": "http.request.completed",
  "timestamp": "2026-11-10T10:15:20.123Z",
  "service.name": "order-service",
  "method": "GET",
  "route": "/api/orders/{id}",
  "status": 200,
  "duration_ms": 127.4,
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "request_id": "req-42",
  "outcome": "SUCCESS"
}
```

This is a **sample schema**, not field names automatically recognized by every backend. If you use OpenTelemetry semantic conventions, check the field names and units for the version in use (for example `http.request.method`, `http.route`, and `http.response.status_code`). When adding structured logging, test end-to-end from encoder → collector → backend, and avoid keeping old names alongside new ones in ways that create duplicate records.

Fields to pay attention to:

- **`method`**: HTTP method, typically low cardinality.
- **`route`**: **route template** like `/api/orders/{id}`, not a raw URL containing IDs/tokens/query strings. If no route matches, use a group like `unmatched` or `not_found`.
- **`status`**: response status code **at the time instrumentation completes**; not necessarily the final status if an error dispatch happens afterward.
- **`duration_ms`**: an integer or decimal number with a clear unit and measurement point; do not put text like `"127 ms"` into a numeric field.
- **`trace_id` / `span_id`**: links logs to existing traces; do not fabricate traces if tracing instrumentation is absent.
- **`request_id`**: a system-controlled ID, not an access token or session ID.
- **`outcome/error_type`**: a standardized error code/category; no need to print exception messages that may contain sensitive data.
- **`instance/environment/version`**: helps distinguish pods or versions when the same endpoint exhibits different latency.

Do not include passwords, Authorization/Cookie headers, raw query strings, bodies, user tokens, or unnecessary PII in summary logs. Be especially careful with `request.getRequestURI()` because **paths themselves can contain secrets**.

## 6. Spring Boot 3: Measuring Synchronous Requests with OncePerRequestFilter

In a **Spring Boot 3 + Spring MVC/Jakarta Servlet + SLF4J** application, you can place the timer in a filter. The example below **only logs summaries for synchronous request dispatches**. It intentionally does not claim to measure the full duration of Servlet async requests—that case is handled separately in the next section.

File `src/main/java/com/example/logging/SyncRequestDurationFilter.java`:

```java
package com.example.logging;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;

@Component
public final class SyncRequestDurationFilter extends OncePerRequestFilter {
    private static final Logger LOG =
            LoggerFactory.getLogger(SyncRequestDurationFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {
        long started = System.nanoTime();
        boolean exceptionEscaped = false;

        try {
            chain.doFilter(request, response);
        } catch (IOException | ServletException | RuntimeException | Error ex) {
            exceptionEscaped = true;
            throw ex;
        } finally {
            if (!request.isAsyncStarted()) {
                long elapsed = System.nanoTime() - started;
                long durationMs = TimeUnit.NANOSECONDS.toMillis(elapsed);

                Object pattern = request.getAttribute(
                        HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
                String route = pattern instanceof String s
                        ? s : "unmatched";

                LOG.info(
                    "event=http.request method={} route={} "
                  + "status={} duration_ms={} exception_escaped={}",
                    request.getMethod(), route, response.getStatus(),
                    durationMs, exceptionEscaped);
            }
        }
    }
}
```

This is a **class for a Spring Boot project with dependencies already configured**, not a standalone Java file compiled with `javac` without a classpath. When running:
- The filter captures the start timestamp before `chain.doFilter(...)`.
- `finally` runs when the chain returns or throws an exception.
- The route comes from `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` if MVC matched a handler; it falls back to `unmatched` otherwise, avoiding raw URLs.
- `response.getStatus()` reflects the **status at the moment the filter logs**; when an exception escapes, the container may perform an ERROR dispatch afterward, resulting in a different final status.
- `exception_escaped` only indicates whether a throwable escaped the filter chain. If an exception is caught and handled by controller advice inside the chain, the flag can be `false` even when the response is 500.
- `TimeUnit.NANOSECONDS.toMillis` **truncates down** to milliseconds. If you want sub-millisecond precision, use floating-point division, but define and standardize the schema format.
- When the request is in async mode after `doFilter`, the example **skips logging duration** to avoid mistaking a partial measurement for the final result. You need framework observation or async lifecycle instrumentation to measure those.

### 6.1. Why Not Just Call `System.nanoTime()` Inside the Controller?

A controller may exclude authentication, rate limiting, earlier filters, argument binding, JSON serialization, response commit, or middleware. Controller duration is useful when measuring handler logic alone, but **it differs from server request duration**. If the requirement is end-to-end on the JVM side, instrumentation must sit outside all components you intend to measure. Filter order, error dispatches, and async lifecycles all affect the scope.

### 6.2. Filter Position in the Chain

Spring Security, CORS, authentication, tracing, compression, routing, and application filters can run before or after your filter. A filter placed **after** authentication will not measure requests rejected early at authentication. If you want to measure 401/403 responses as well, the instrumentation must wrap the required scope with appropriate filter order/registration configuration.

Do not change filter order arbitrarily just to log a few extra milliseconds: moving a filter can affect security, MDC, or lifecycle behavior. Define your measurement requirements first and test 2xx/3xx/4xx/5xx branches.

## 7. Major Pitfall: Servlet Async, DeferredResult, and Streaming

For endpoints returning `Callable`, `DeferredResult`, or using Servlet async, `chain.doFilter(...)` can **return before the request actually completes**.

Example:

```text
00 ms: Filter starts, chain.doFilter(...)
02 ms: Controller starts async and returns control
03 ms: chain.doFilter(...) returns to filter
...
240 ms: async task completes with result
245 ms: response is sent and async lifecycle completes
```

If you log duration in `finally` at the 03 ms mark, the log will report **3 ms**, while the server continues processing the request until around 245 ms. This makes a slow request look very fast. To avoid this, the sample filter above skips the summary when `request.isAsyncStarted()`.

**`OncePerRequestFilter` does not mean an HTTP request executes the filter only once in every scenario.** Spring documents that it runs once **per dispatch**; REQUEST, ASYNC, and ERROR dispatches can happen on different threads. By default `shouldNotFilterAsyncDispatch()` is `true`; ERROR dispatch also has its own option. Changing flags or dispatcher mappings alone does not solve timing lifecycle issues without proper state and completion hooks.

### 7.1. The Right Way for Servlet Async

Prefer the **framework's HTTP server observation** when available. If you must implement Servlet async timing yourself, you need to:
1. Store **one monotonic start timestamp** on initial request receipt; do not reset it on each async redispatch.
2. Track **final completion** using the appropriate lifecycle mechanism (e.g., `AsyncListener.onComplete` or a framework-provided completion abstraction).
3. Emit **one** summary per request, even across multiple dispatches, using a guard such as `AtomicBoolean.compareAndSet`.
4. Handle `onTimeout` and `onError` to record appropriate status/metrics, but **do not assume they are always the final end point**; the container may continue with an error dispatch.
5. When `onStartAsync` starts a new async cycle, the listener may need to be re-registered per the Servlet contract.
6. Ensure filter registration policies include the required dispatcher types; do not just override one method and assume the entire pipeline works.
7. Verify final status, request ID, MDC, and thread context after async; do not use a `ThreadLocal` on a worker thread assuming it belongs to the original request.
8. Test timeouts, client disconnects, exceptions, restarts, and successful completions.

The `onComplete`, `onTimeout`, `onError`, and `onStartAsync` callbacks belong to `jakarta.servlet.AsyncListener`. A few-line snippet attaching a listener is **not enough** for a production solution if the branches above are not handled; using framework-supported observation is usually less error-prone.

### 7.2. Spring WebFlux and Reactive Streams

Spring WebFlux uses reactive `Mono`/`Flux` chains. The moment a method returns a `Mono` **is not** when the publisher completes or the response is sent. Do not measure duration by calling `System.nanoTime()` before/after a method that merely constructs a publisher. You must instrument at subscription/termination or use built-in HTTP server observation. For streaming/SSE, a long-lived request can be **normal behavior**; the definition of "completion duration" must clarify whether it means time to first byte, stream completion, or disconnect.

## 8. Spring Boot Actuator/Micrometer: Metrics Do Not Replace Logs, and Vice Versa

Spring Framework/Micrometer supports an observation commonly named `http.server.requests` for server-side HTTP exchanges; when Actuator/metrics and the appropriate components are enabled, you can get timers/histograms tagged by HTTP method, route template, and status/outcome. In Spring Boot 3, the Observation system is integrated with Spring MVC/WebFlux instrumentation.

Do not write a custom duration-measuring filter **just to get p95/p99** if the system already has framework timers. Two measurement layers with different scopes can produce two numbers that confuse operations teams. Start by checking:
- Is Actuator/Observation enabled?
- What are the actual meter names and tags in the running framework version?
- Are any routes skipped because errors occur before handler matching?
- Are there async or streaming requests that need separate categorization?
- Are both HTTP server and HTTP client metrics present, and is a dashboard mixing them up?

`http.server.requests` typically measures the **server** side; `http.client.requests` measures outbound HTTP client calls. Do not compare a client metric with a server metric and claim the request "lost time" without accounting for network, proxy, and retries.

### 8.1. Timers Measure Count and Total Time; Histograms Measure Distribution

Micrometer `Timer` is designed for durations. It can record:
- Event `count`.
- Total time `totalTime`.
- Max time or windowed statistics, depending on implementation.
- Percentiles/histograms when configured and supported by the backend.

Code example **for illustration when the project already has Micrometer**:

```java
Timer timer = Timer.builder("app.operation.duration")
        .description("Time spent processing an application operation")
        .tags("operation", "lookup")
        .register(meterRegistry);

Timer.Sample sample = Timer.start(meterRegistry);
try {
    performLookup();
} finally {
    sample.stop(timer);
}
```

This snippet is not a standalone Java file: it requires `io.micrometer.core.instrument.Timer`, a `meterRegistry` variable, and a `performLookup()` method. `Timer.Sample` measures elapsed time using the registry's clock; `stop(timer)` records the sample after the work finishes.

In Spring Boot, HTTP request observation may already create a timer; you do not necessarily need a custom timer wrapping the same scope. If you want statistics for sub-operations, use a distinct metric name and clearly document its scope.

### 8.2. Why Averages Are Not Enough

Suppose there are 100 requests:
- 95 requests complete in about 40 ms.
- 5 requests take about 2,000 ms.

The average can look relatively low compared to the severely slow group, while users in the tail still experience high latency. Using **p50, p95, and p99** alongside throughput and error rate gives a much fuller picture.

**p95** is the level that roughly 95% of observations **do not exceed** under the corresponding percentile definition; **p99** focuses further into the tail. Estimated percentiles can differ by algorithm, time window, and backend.

Micrometer distinguishes:
- **Percentile histograms**: record buckets so a compatible backend can compute approximate percentiles and aggregate across dimensions.
- **Client-side percentiles**: computed inside a single meter in the application, which are difficult or impossible to aggregate accurately across multiple pods.
- **A single slow-request log line**: helps inspect a specific request, but cannot be used to derive p99 for overall traffic.

Limit cardinality: do not attach `request_id`, `user_id`, raw URL `/orders/42`, email, or tokens as **metric labels**. Use `http.route=/orders/{id}`, method, status class, service, and other bounded-value labels.

### 8.3. What Signals Should a Dashboard Combine?

| Signal | Question it answers |
| --- | --- |
| Request rate | How many requests per second? |
| Error rate / status mix | How are 4xx/5xx changing? |
| p50/p95/p99 latency | How are median/tail users affected? |
| Histogram buckets/SLO | How many requests fall below 100/300/1000 ms thresholds? |
| Slow-request logs | Which specific requests were slow, with what route/trace/status? |
| Distributed traces | Is time spent in DB, downstream, queue, serialization, or app code? |
| Resource metrics | Are CPU/GC/thread pool/DB pool saturated? |

Do not use logs alone to build percentile charts if the log pipeline has sampling or drops; otherwise the sample is unrepresentative unless designed to be calibrated.

## 9. Request Duration Logging Policy: Every Request or Only Slow Requests?

Depending on traffic volume and investigation needs, you can choose:

1. **Summary for every request**: suitable for small services or approved audit requirements; easy to trace, but incurs significant disk, network, and ingest costs.
2. **Slow requests only**: keep events exceeding a threshold, such as `duration_ms >= 500`; reduces noise but loses some context about fast requests.
3. **Sample normal requests, keep slow/error requests**: supports investigation at high traffic; requires recording the sampling rate and not treating log counts as absolute counts.
4. **Full metrics + threshold-based logs + appropriately sampled traces**: usually a good balance between observability and cost.

An illustrative policy:

```text
IF status >= 500:
    log WARN/ERROR summary (without repeating unnecessary stack traces)
ELSE IF duration_ms >= 1000:
    log WARN event=http.request.slow
ELSE IF sample normal request:
    log INFO event=http.request.completed
ELSE:
    no detailed event needed; still record timer metrics
```

The threshold is only an example; `1000 ms` is not a universal standard for all APIs. Categorize by route, method, and SLO targets. A streaming endpoint can run for minutes without being considered an error; a critical auth endpoint may need a much tighter limit.

**Do not let the logging thread perform heavy I/O on the critical path just to measure latency.** If a synchronous appender writes slowly, it can inflate duration and impact the request itself. Async logging also has queue-full/drop policies: if logs are dropped under heavy load, p99 derived from logs will miss the worst requests.

## 10. How to Measure Without Skewing Results

Several instrumentation mistakes can distort measurements:

### 10.1. Wrong Start/End Placement

- Starting the timer **after** authentication: misses requests rejected early with 401/403.
- Stopping before JSON serialization: misses the cost of converting objects into the response.
- Stopping at controller return when Servlet async has just started: measures a far too short interval.
- Wrapping too many layers: the "server duration" metric accidentally includes work unrelated to the HTTP request.
- Measuring at the gateway and comparing with a Spring filter without noting the scope difference.

### 10.2. Double Logging / Double Instrumentation

If container access logs, a Spring request filter, a gateway, and a Collector all emit logs for one request, dashboards may see multiple records and mistake them for duplicate requests. Distinguish event/scope names (`gateway.request`, `http.server.request`, `handler.duration`) instead of merging them into one statistic. Do not attach an extra filter timer duplicating Actuator and sum them twice.

### 10.3. Logging Too Much Data

A request duration summary **does not need** Authorization headers, Cookies, request bodies, response bodies, or raw query strings. Printing an entire `HttpServletRequest` object or exception can expose sensitive data. Logging method, route template, status, duration, request/trace ID, and approved outcome is sufficient for most cases.

### 10.4. Precision and Overhead

- Short durations under 1 ms will show `duration_ms=0` if cast to a `long` millisecond.
- Use floating-point with 3 decimal places if µs-level readability is needed; keep the schema consistent.
- `System.nanoTime()` has a small but non-zero cost; regexes, formatting, and MDC/JSON encoding often consume far more CPU.
- Do not benchmark with a single request. Use load testing and compare a baseline with instrumentation enabled vs. disabled.
- Do not include objects with expensive `toString()` methods in log messages, especially on every request.

## 11. Analyzing Timeouts and Errors

A slow request can lead to a 504 at the proxy or 503/500 at the server, but **not every timeout happens inside the Java application**.

| Scenario | What might you see? | What to correlate |
| --- | --- | --- |
| Client times out before server finishes | Client reports timeout, server may continue | Client deadline, server completion, disconnect |
| Gateway timeout 504 | Proxy timed out waiting for upstream | Proxy timer and server logs/traces |
| DB pool exhaustion | Request waits to acquire a connection before querying | Pool wait, active/idle connections, JDBC metrics |
| Outbound HTTP retry | Server duration is larger than a single downstream call | Retry count, trace spans, timeout budget |
| JVM GC pause | Many requests spike in duration simultaneously | GC logs, CPU, thread scheduling |
| Thread pool saturation | Request queuing or scheduling delays | Executor queue, pending tasks |
| Servlet async timeout | Work did not finish before deadline | Async lifecycle, onTimeout/onComplete |
| Client disconnect | Server write fails or request is cancelled | I/O errors, cancellation signals |
| Early 4xx validation | Very fast request | Filter order, body parsing, auth branch |

When logging duration in `finally`, an exception can **escape** and be handled later by Spring Security, an exception resolver, or the servlet container. `response.getStatus()` inside the filter is not necessarily the final status. If you need the guaranteed final status for metrics, use the appropriate lifecycle completion point and test ERROR dispatches.

For cancelled requests, do not assume "status 200 in the response object" means the client received all bytes. Server-side duration and client experience can differ.

## 12. Traces Help Break Down Request Duration in Detail

A server request lasting 950 ms might consist of:

```text
http.server 950 ms
  auth/check        18 ms
  DB connection    240 ms
  SQL query        510 ms
  serialize JSON    42 ms
  other/overlap     ...
```

These timings are **illustrative**; you should not blindly sum all span durations because spans can **overlap or run in parallel**. Traces show parent-child relationships and causal ordering; summary logs can include `trace_id` to navigate to the trace.

A useful log:

```text
WARN event=http.request.slow method=GET route=/api/orders/{id} status=200 duration_ms=950 trace_id=4bf92f3577b34da6a3ce929d0e0e4736
```

Then inspect in the trace:
- Waiting for a DB connection or executing SQL?
- Which HTTP client call took time?
- Were there retries/backoff?
- Were there concurrent tasks or lock contention?
- Was there queuing before the handler/worker?
- Was there an error/timeout whose exception was caught and handled?

A Trace ID only helps with correlation; it does not by itself prove the request duration has the right scope. Span timings also require proper clocks and instrumentation.

## 13. Cardinality and Privacy Issues When Attaching Routes

For web APIs:

```text
/api/orders/41
/api/orders/42
/api/orders/43
```

If you use the raw path as a metric tag, every order ID creates **a new time series**. This increases memory, storage, and query costs. Similarly, user IDs, trace IDs, request IDs, and query strings are very high-cardinality labels.

Use this instead:

```text
method=GET route=/api/orders/{id} status=200
```

Even in logs (not just metrics), raw paths can contain tokens in password-reset links or personal data. In Spring MVC, `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` can provide the route template after mapping; when unmatched, use a label like `unmatched` instead of falling back to the raw URI.

Standardize route templates across Spring MVC, WebFlux, gateways, and tracing instrumentation; if each layer names routes differently, cross-service latency analysis becomes difficult. Do not dump raw request headers/cookies into logs just to figure out which endpoint is slow.

## 14. Request Duration Testing Checklist

| Case | Expectation |
| --- | --- |
| Synchronous GET 200 | One summary, non-negative duration, correct unit |
| POST 400 from validation | Counted if within instrumentation scope |
| 401/403 from Spring Security | Counted **if** filter/observation is placed early enough |
| 500 from exception | Duration is logged, outcome/status reflects lifecycle accurately |
| Exception caught by handler | Do not infer outcome solely from "exception escaped" |
| Servlet `Callable` / `DeferredResult` | Do not confuse returning from `doFilter` with HTTP completion |
| Async timeout | One final result, no double logging across dispatches |
| Servlet ERROR dispatch | Does not produce two unintended summaries |
| WebFlux `Mono` / `Flux` | Measure publisher completion/cancellation properly, not Mono creation |
| Streaming/SSE | Duration contract distinguishes first byte from stream completion |
| Gateway 504 | Compare gateway and server timestamps; do not assume identical timeouts |
| Slow outbound HTTP/DB | Sub-traces/metrics help categorize |
| Route with ID or token | Log only the template, never the raw URL |
| Parallel load | p95/p99 histograms, RPS, and error rate are verifiable |
| Blocked log appender | Do not mistake logging slowness for business logic slowness |
| Late collector ingest | Do not confuse event timestamp with observed/ingest time |

### 14.1. A Unit Test for the Duration Formula

From `RequestDurationDemo` above, a fake clock fixed two pairs of timestamps. In production unit tests, you can inject a `LongSupplier`/clock abstraction and assert the difference and log fields **without using `Thread.sleep(...)`**. Sleep makes tests slow, flaky, and scheduler-dependent.

Spring Boot integration tests should start a real server or use `MockMvc` according to the appropriate scope to verify filter order, error handling, and route templates. For Servlet async, use a test that genuinely triggers async and completes the response; synchronous controller tests do not prove async instrumentation works.

## 15. Troubleshooting Workflow for "Duration Logs Don't Match"

1. **Identify the two numbers** being compared: client, gateway, server observation, filter, or controller timer.
2. **Compare start/end points** of each tool; do they include network, auth, serialization, and async lifecycle?
3. **Check units and precision**: ns, µs, ms, s; integer truncation vs. floating point.
4. **Check the clock**: does elapsed time use `nanoTime` or wall-clock? Are timestamps compared across different machines?
5. **Check filter order/dispatches**: are 401/403, exceptions, ERROR, or ASYNC dispatches skipped or double-counted?
6. **Correlate method, route template, status, trace ID, and instance** to confirm the same request/scope.
7. **Check the pipeline**: are log appender queues, Collector delays, query sorting, or sampling/drops delaying or omitting records?
8. **Find the real bottleneck**: traces, DB pool, GC, thread pool, network, retries.
9. **Check the dashboard**: which histogram computes p95/p99, and does it aggregate correctly across instances and dimensions?
10. **Reproduce with a controlled workload**, keeping source logs, metrics, and traces.

Do not "fix" discrepancies by subtracting an arbitrary constant or adding `Thread.sleep`. Measure the right scope and label metric/log names clearly.

## 16. Common Mistakes and How to Prevent Them

**Mistake 1 — using `System.currentTimeMillis()` for elapsed time:** the clock can be adjusted; use `System.nanoTime()` and convert units properly.

**Mistake 2 — measuring a controller and calling it "request duration":** skips middleware/serialization; name it `handler_duration_ms` or move the measurement point.

**Mistake 3 — treating `finally` on Servlet async as the end point:** undercounts duration; use observation or completion lifecycle hooks and ensure a single write.

**Mistake 4 — logging final status before ERROR dispatch:** `response.getStatus()` may not be the final status; define which lifecycle point determines status.

**Mistake 5 — using raw paths as metric labels:** causes high cardinality and risks leaking tokens; use bounded-value route templates.

**Mistake 6 — computing p99 from a few slow-request logs:** the sample misses normal events and may have drops; use timer histograms for statistics.

**Mistake 7 — logging every request with payloads/headers:** increases overhead and privacy risk; summaries should contain safe metadata.

**Mistake 8 — measurements skewed by logging itself:** a blocked synchronous appender or excessive formatting increases latency; measure overhead and consider async policies.

**Mistake 9 — comparing durations of different scopes:** 500 ms on the client and 250 ms in the handler do not contradict each other when TLS/network/proxy/serialization are involved.

**Mistake 10 — summing span durations:** spans can be nested or concurrent; use critical path/trace topology rather than naive addition.

**Mistake 11 — missing correlation IDs:** hard to tell which request a slow log belongs to; use securely generated trace/request IDs.

**Mistake 12 — duration metrics without error/status context:** p95 rises without showing whether 5xx or specific routes caused it; choose sensible low-cardinality tags.

## 17. Implementation Decision Summary

When implementing **Request duration** logging in a Java web application, a practical sequence is:

1. Define the exact **start/end/scope** of the duration.
2. Use a monotonic clock for elapsed time and a separate timestamp for event time.
3. Prefer built-in framework **HTTP server Observation/Micrometer** to measure the full request lifecycle, especially for async/WebFlux.
4. If writing a custom request summary, verify filter order, exceptions, async dispatches, status handling, and duplicate prevention.
5. Log method, route template, status/outcome, duration, trace/request ID, and approved service metadata.
6. Use timers/histograms for p50/p95/p99, request rate, and SLOs; use logs for investigating individual requests.
7. Monitor overhead, queue-full/loss behavior, cardinality, privacy, and retention.
8. Test sync, error, timeout, async, streaming, multi-instance, and collector ingest paths.

**Remember:** a `duration_ms` number is only valuable when it measures a clearly defined interval. In web logging, measure with the right clock, finish at the right lifecycle point, and correlate with route/status/trace—rather than wrapping a single method with a timer and calling it total HTTP latency.

## References

- [Oracle Java – System.nanoTime()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime()).
- [Oracle Java – TimeUnit](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/TimeUnit.html).
- [Spring Framework – OncePerRequestFilter and async/error dispatch](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html).
- [Jakarta Servlet 6.0 – AsyncListener lifecycle](https://jakarta.ee/specifications/servlet/6.0/jakarta-servlet-spec-6.0.html).
- [Spring Framework – Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html).
- [Spring Boot – Metrics / http.server.requests](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
- [Micrometer – Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).
- [Micrometer – Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html).
- [OpenTelemetry – HTTP semantic conventions](https://opentelemetry.io/docs/specs/semconv/http/http-metrics/).
- [OpenTelemetry – Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/).
