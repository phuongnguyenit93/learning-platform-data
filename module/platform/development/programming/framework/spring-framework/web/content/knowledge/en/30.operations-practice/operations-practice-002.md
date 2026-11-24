# Observing Requests/Responses with Logs, Tracing, and Micrometer Observation in Spring Web

A Spring MVC endpoint might return `200 OK` while users still perceive it as slow; another request might end in `500` while the log only says "Something went wrong." To find the root cause, you need to know **which request entered the system, which components it passed through, how long it took, what status it returned, what error occurred, and whether related records can be correlated**.

Observability is not just about printing more logs. In Spring Framework 6.1/Spring Boot 3.3, three signal sources typically work together: **logs**, **metrics**, and **distributed traces**. Micrometer Observation provides a unified recording layer: through corresponding `ObservationHandler`s, a single observation can produce meters/metrics and spans, while logging describes specific application events. This lesson focuses on requests/responses in **Spring MVC on the Servlet stack**, contrasting HTTP client boundaries and cross-service tracing where relevant.

## 1. From a single request to three kinds of evidence

Suppose the application has an endpoint `GET /api/items/42`. Looking at the three signals:

| Signal | What question does it answer? | Example content | Scope and limitations |
| --- | --- | --- | --- |
| **Log** | "What happened during this specific execution?" | "start lookup", "lookup failed", exception stack trace, `traceId` | Detailed, roughly ordered; without correlation it is hard to join multiple lines/services |
| **Metric** | "What is the rate, duration, and error ratio across many requests?" | Count, total/latency stats of `http.server.requests` by method/status/URI template | Cheap to aggregate/trend; does not describe individual executions |
| **Trace** | "Which services/spans did a specific execution pass through, and where was time spent?" | Trace A has server span → client span → downstream server span | Requires a tracer, context propagation, and backend; sampling may omit some requests |

Investigation example: an alert fires for rising p95 latency on `GET /api/items/{id}` from metrics; filter slow traces to see that the span calling the catalog service takes most of the time; use that trace's `traceId` to inspect logs and find the specific cause. **Do not use a metric to reconstruct individual request details, and do not use scattered logs in place of aggregated error rates.**

```text
Client
  └─ HTTP GET /api/items/42
      ├─ Servlet filter / Spring MVC
      │   ├─ HTTP server Observation: http.server.requests
      │   │   ├─ ObservationHandler → metric timer
      │   │   └─ tracing handler → server span (when tracer present)
      │   ├─ Controller/Service → application logs
      │   └─ HTTP response 200
      └─ HTTP client / network response

Operator
  ├─ metrics → request volume, duration, status, URI groups
  ├─ traces  → span relationships and timing on a single trace
  └─ logs    → events, errors, details for investigation
```

The name `http.server.requests` is the observation/meter name in the default Spring Framework 6.1 configuration. Backends such as Prometheus may change meter naming conventions upon export. Do not assume a Prometheus metric name is identical verbatim to the observation name.

## 2. Starting with meaningful request/response logs

### 2.1. Logging at the right level

Logs can be placed in controllers/services to describe genuinely valuable events: starting processing, taking an important branch, business outcomes, or errors needing triage. When you need an overview of every HTTP request, use a filter or server/proxy access logs rather than scattering `log.info` into every controller. Each observation source has a different scope:

- **Application log:** the controller/service knows the business context and root cause; a filter knows HTTP method/status but does not inherently know all business details.
- **Servlet filter log:** can record method, route, status, and duration; filter/dispatch order affects what is recorded, especially for async requests.
- **Container access log:** records HTTP transactions from the server's perspective; format and configuration depend on Tomcat/Jetty/Undertow.
- **Proxy/ingress log:** reflects requests blocked or failing directly at the proxy, which may never reach the Java application.

Do not enable debug logging for full bodies, tokens, cookies, or `Authorization` headers in production. URLs can contain emails, IDs, or sensitive queries; prefer the **route template** `/api/items/{id}` over the raw URL when logging for aggregation. If detailed logging is needed for incident triage, explicitly define allowed fields, retention level, and access control.

### 2.2. Example controller with business logging

Assume a Spring Boot 3.3/Java 17+ application with `spring-boot-starter-web` and `spring-boot-starter-actuator`. File `src/main/java/com/example/observe/ObserveApplication.java`:

```java
package com.example.observe;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ObserveApplication {
    public static void main(String[] args) {
        SpringApplication.run(ObserveApplication.class, args);
    }
}
```

File `src/main/java/com/example/observe/ItemController.java`:

```java
package com.example.observe;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/items")
public class ItemController {
    private static final Logger log =
            LoggerFactory.getLogger(ItemController.class);

    private final ItemService service;

    public ItemController(ItemService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public ResponseEntity<ItemDto> find(@PathVariable long id) {
        log.debug("Looking up item");
        String label = service.findLabel(id);
        log.info("Item lookup completed");
        return ResponseEntity.ok(new ItemDto(id, label));
    }

    public record ItemDto(long id, String label) {}
}
```

The example intentionally omits `id` from the log. Once the system has proper authorization and data classification, approved identifier keys may be logged, but not every `@PathVariable` should be assumed safe to log.

File `src/main/java/com/example/observe/ItemService.java`:

```java
package com.example.observe;

import org.springframework.stereotype.Service;

@Service
public class ItemService {
    public String findLabel(long id) {
        return "Item-" + id;
    }
}
```

The request `GET /api/items/42` is expected to return JSON equivalent to `{"id":42,"label":"Item-42"}` and status 200. That is the logical result of the sample code; JSON field ordering is not a guaranteed contract without additional configuration.

Log levels can be configured as:

```properties
logging.level.root=INFO
logging.level.com.example.observe=DEBUG
```

Setting `DEBUG` on the application's own package clarifies events without turning on DEBUG logs across all of Spring. In real environments, `INFO` logging on every request can create high volume; consider relying on metrics/access logs for routine statistics and keeping business logs at appropriate levels.

### 2.3. If writing a filter, respect the Servlet lifecycle

When a controller-independent request summary is needed, a minimal `OncePerRequestFilter` can log method, status, and duration for normal dispatches. The following example is a **snippet illustrating safe field selection**, not a replacement for standard Micrometer instrumentation:

```java
// Inside doFilterInternal(...) of OncePerRequestFilter:
long started = System.nanoTime();
try {
    filterChain.doFilter(request, response);
} finally {
    long elapsedMs = java.util.concurrent.TimeUnit.NANOSECONDS
            .toMillis(System.nanoTime() - started);

    Object matchedPattern = request.getAttribute(
            org.springframework.web.servlet.HandlerMapping
                    .BEST_MATCHING_PATTERN_ATTRIBUTE);

    String route = matchedPattern instanceof String pattern
            ? pattern
            : "UNMATCHED";

    logger.info("method={} route={} status={} durationMs={}",
            request.getMethod(), route, response.getStatus(), elapsedMs);
}
```

The snippet above is not a standalone Java class: it must sit inside a filter subclass that defines `logger` and receives `request`, `response`, and `filterChain`. With async Servlets, the timing in `finally` may only reflect when the dispatch finishes, not when the final response finishes sending. To measure the full HTTP lifecycle accurately, prefer built-in Servlet server instrumentation with appropriate dispatch configuration.

Do not manually create an additional `Observation` named `http.server.requests` around every request **when** `ServerHttpObservationFilter` is already active; that can duplicate metrics/spans and skew numbers.

## 3. Micrometer Observation: the unified recording unit

Micrometer distinguishes these components:

- `ObservationRegistry`: registry that receives/coordinates observations; without an effective handler, an observation may produce neither metrics nor spans.
- `Observation`: a named activity span with start/end times and a context.
- `Observation.Context`: holds context for observation processing (including error state and key-values).
- `ObservationConvention`: defines names/contextual names and tags (key-values) suited to each observation type.
- `ObservationHandler`: receives lifecycle events, such as integrating metric recording and trace span creation.
- `ObservationFilter`: customizes key-values/context when an observation finishes; distinct from a Servlet Filter.

An HTTP server observation usually wraps a request/response exchange; the default name in Spring MVC is `http.server.requests`. Beyond automatic observations, you can explicitly observe a business segment when you need visibility into its duration.

File `src/main/java/com/example/observe/ObservedCatalog.java`:

```java
package com.example.observe;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class ObservedCatalog {
    private final ObservationRegistry registry;

    public ObservedCatalog(ObservationRegistry registry) {
        this.registry = registry;
    }

    public String loadCategory() {
        return Observation.createNotStarted(
                        "catalog.load", registry)
                .lowCardinalityKeyValue("operation", "read")
                .observe(() -> "general");
    }
}
```

`.observe(Supplier<T>)` wraps the execution: it starts the observation, runs the supplier, and stops the observation even if the supplier throws an exception (according to the API's lifecycle semantics). With `spring-boot-starter-actuator`, Spring Boot auto-configures the registry/handler infrastructure for capabilities present on the classpath. The example uses its own name `catalog.load`, so it **does not replace** the HTTP metric `http.server.requests` provided by the Framework.

For workloads that can fail, prefer `observe(...)` or proper `try`/`finally` lifecycle handling rather than calling `start()` and forgetting `stop()`. An abandoned observation causes durations/traces to misrepresent reality.

### 3.1. Cardinality: the prerequisite for usable metrics

**Low cardinality** is a value set of finite, stable size. Good examples: `method=GET`, `status=200`, `uri=/api/items/{id}`, or `operation=read`. These tags are well suited as metric dimensions.

**High cardinality** is a value set that can grow with the number of requests, such as `itemId=42`, `userId=abc123`, URLs containing IDs, or request IDs. Putting them into a **metric tag** can cause time-series explosion, increasing memory, storage cost, and overload risk. Micrometer Observation distinguishes:

| Key-value type | Metric | Trace | Example |
| --- | --- | --- | --- |
| `lowCardinalityKeyValue` | Can become a tag/dimension | Can become a span attribute | `operation=read` |
| `highCardinalityKeyValue` | Does not automatically become a meter tag | Can become a span attribute | `itemId=42` if allowed to store |
| Log field | Does not automatically become a metric tag | Does not automatically appear in traces | Business events and stack traces |

This does not mean high-cardinality trace tags are always safe: tracing backends also have costs and security policies. Personal values/secrets can leak via spans; filtering/redaction rules similar to logging must apply.

## 4. Automatic HTTP server observation in Spring MVC

Spring Framework supports `ServerHttpObservationFilter` (a Servlet filter) to create server observations for requests/responses. In a plain Spring Framework application, the filter must be registered with an active `ObservationRegistry`. Spring Boot Actuator typically auto-configures these components when the corresponding dependencies and observability features are present.

Common tags under the default Spring Framework 6.1 convention:

| Tag | Content | Why it is useful |
| --- | --- | --- |
| `method` | HTTP method such as GET/POST | Compare traffic and latency by method |
| `uri` | Handler's **URI pattern** if determinable | Aggregates `/api/items/42`, `/api/items/43` into one route |
| `status` | HTTP response status, e.g., 200/404/500 | Distinguishes success and failure at the HTTP level |
| `outcome` | Exchange outcome group | Tracks status groups |
| `exception` | Observed exception or `none` | Finds unhandled failures within the observation scope |

Tag count, types, and names may vary across versions/conventions/backends. Notably, **status 500 does not automatically imply `exception=SomeException`**. When `@ExceptionHandler` handles an exception and converts it into a normal response, the exception may not escape through the Servlet observation filter to be recorded as an error. Distinguish **HTTP response status**, **business errors**, and **throwables observed by instrumentation**.

Unmapped requests or redirects may be assigned fallback URI values such as `NOT_FOUND`, `REDIRECTION`, or `UNKNOWN` depending on convention. Therefore, route-based queries are only accurate when routing information can be determined by instrumentation.

Spring MVC **does not automatically include everything**: upstream proxy filters, browser networking, TCP handshakes, browser render time, and uninstrumented external dependencies will not produce proper spans merely because HTTP server observation exists.

## 5. Building a verifiable check with Actuator

With Boot 3.3, typical Gradle dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

This snippet adds to a project that already has the Spring Boot plugin and dependency management. In an internal dev environment, the metrics endpoint can be enabled:

```properties
spring.application.name=web-observe-demo
management.endpoints.web.exposure.include=health,info,metrics
```

By default, Actuator endpoints exposed over HTTP are very restricted; `metrics` must be explicitly exposed in configuration. Typical URLs:

```bash
curl -i http://localhost:8080/api/items/42
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/http.server.requests
```

The first action generates a request, the second lists recorded meter names; the third (when data/handlers exist) returns measurements/tags for `http.server.requests`, such as `COUNT` and `TOTAL_TIME`. **Do not hardcode measurement numbers** because they vary with traffic and runtime. To filter by a tag:

```bash
curl -G "http://localhost:8080/actuator/metrics/http.server.requests" \
  --data-urlencode "tag=method:GET" \
  --data-urlencode "tag=uri:/api/items/{id}"
```

The commands above assume a shell supporting `\` line continuations like Bash. On Windows PowerShell, run on one line or use PowerShell line-continuation rules. The metrics endpoint response is Actuator JSON; the meter name used in the URI is the base name `http.server.requests`, which does not necessarily match the name exported to Prometheus.

**Limitation:** this only checks instrumentation/metrics at a single application instance, not a centralized monitoring system. For long-term collection, you need a configured meter registry/exporter (Prometheus, OTLP, etc.), storage backend, and dashboards/alerts. Actuator endpoints can expose sensitive operational data, so restrict network access and authorization when exposing them in real environments.

### 5.1. Verifying with an integration test

In the simple application above, you can verify that a real HTTP request records an HTTP server meter in `MeterRegistry`. File `src/test/java/com/example/observe/HttpObservationTest.java`:

```java
package com.example.observe;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
class HttpObservationTest {
    @Autowired
    TestRestTemplate http;

    @Autowired
    MeterRegistry meters;

    @Test
    void realRequestRecordsHttpServerTimer() {
        var response = http.getForEntity("/api/items/42", String.class);
        assertTrue(response.getStatusCode().is2xxSuccessful());

        Timer timer = meters.find("http.server.requests")
                .tags("method", "GET", "uri", "/api/items/{id}")
                .timer();

        assertNotNull(timer);
        assertTrue(timer.count() >= 1L);
    }
}
```

This test assumes default Actuator/Micrometer HTTP server observation configuration and an application with only the simple endpoints above. It proves **a request was sent through the embedded HTTP server** and recorded by the meter at least once; it does not prove traces were sent to a collector, logs contain MDC, or downstream propagation works. Tests calling controller methods directly usually do not create server observations; with `MockMvc`, whether events are recorded depends on instrumentation/filter setup in the test context, so do not assume equivalence to live HTTP.

Run the check with:

```bash
./gradlew test --tests com.example.observe.HttpObservationTest
```

On Windows use `.\gradlew.bat test --tests com.example.observe.HttpObservationTest`. This is an instruction for running the example test; it is not a claim that the test was executed in a specific project.

## 6. Distributed tracing: trace/span and correlation ID

A **trace** represents a chain of operations related to a single request across multiple components. Each **span** is one segment of that chain, typically sharing a trace ID while having its own span ID and parent/child relationship:

```text
Trace ID: abc...
  [HTTP SERVER GET /api/items/{id}]        60 ms
      ├─ [catalog.load]                    15 ms
      └─ [HTTP CLIENT GET /inventory/{id}]  38 ms
            └─ [inventory: HTTP SERVER]    30 ms
```

Timings and IDs in the diagram are illustrative only, not actual measurements. Do not sum spans in the diagram as a substitute for request duration; spans can nest or execute in parallel. To get distributed traces, both client and server sides of cross-service calls must be instrumented and **propagate trace context** properly.

Micrometer Observation only turns into trace spans automatically when a matching tracing handler/tracer is on the classpath and in the registry. Adding `spring-boot-starter-actuator` alone is not enough to view traces in a backend. With Boot 3.3, an OpenTelemetry tracing setup exporting to Zipkin can use:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-zipkin'
}
```

This example adds tracer/exporter configuration **on top of** the web app from the previous section and requires a running Zipkin collector. You can choose the Brave bridge or another backend as required; do not mix multiple bridges/exporters unintentionally. In Boot 3.3, Zipkin configuration properties have the form `management.zipkin.tracing.*`; do not assume they match newer Boot versions verbatim.

So every sample request has a chance to be recorded while learning tracing locally:

```properties
management.tracing.sampling.probability=1.0
management.zipkin.tracing.endpoint=http://localhost:9411/api/v2/spans
```

Spring Boot 3.3 defaults to roughly 10% sampling; `1.0` records more traces and is only sensible for low-traffic verification environments. In production, choose sampling based on traffic, cost, and investigation needs. **Not seeing a trace in the backend does not prove the system failed to process the request**, as the request may not have been sampled, the exporter/collector may be down, or context may not have propagated across services.

### 6.1. Correlation IDs in logs

When Micrometer Tracing is configured, Spring Boot can populate `traceId` and `spanId` into MDC (Mapped Diagnostic Context) for logs on threads with an active span. Example log format:

```text
2026-10-21 INFO [abc123-traceIdLikeValue-def456] Item lookup completed
```

This is a **format illustration**, not a valid trace ID you can look up from a real request. In real configurations, use the trace ID/format generated by your tracer and logging pattern. A single trace can contain multiple span IDs; two lines from different services sharing a `traceId` do not necessarily share the same `spanId`.

For investigation, an effective workflow is grabbing the `traceId` from the trace backend and searching for all logs with that ID in the corresponding time window. If you only add an independent random `requestId` per service, the system must propagate that ID itself; it does **not automatically** create parent/child relationships or durations like distributed tracing.

### 6.2. Propagating context when calling other services

Spring Boot auto-configures observation/tracing for certain HTTP client builders. For example, when calling another backend:

```java
// Illustrative snippet inside a @Service with an injected RestClient.
RestClient client = builder.baseUrl("http://localhost:8081").build();
String response = client.get()
        .uri("/inventory/{id}", 42)
        .retrieve()
        .body(String.class);
```

Here `builder` is a `RestClient.Builder` **provided by Spring Boot** via dependency injection. Tracing infrastructure can automatically propagate W3C trace context or the configured propagation format. If you call `RestClient.create()` or `new RestTemplate()` manually, bypassing the auto-configured builder without attaching the observation registry/interceptor, automatic propagation can be lost. Always verify downstream traces, not just logs on the calling service.

For `@Async`, task executors, thread pools, virtual threads, or reactive pipelines, context/thread-local/MDC is **not guaranteed** to follow every thread hop automatically. Use the context propagation mechanism supported for your version/execution model and test across thread boundaries. Copying MDC manually and forgetting to clear/restore it can also "bleed" IDs from one request into another.

## 7. Tracking errors and responses reliably

A server observation can record HTTP 4xx/5xx statuses, while the `error` state in traces/tags depends on whether an exception passed through the instrumentation layer or was already handled. For example, a controller using `@ExceptionHandler` turns an exception into a 404 response; the Servlet filter observation sees status 404 without **seeing an escaping exception**.

Therefore, when diagnosing errors, combine:

1. **Metrics by HTTP status/outcome:** which endpoint saw rising 5xx or duration?
2. **Application logs where exceptions are handled:** are error codes and stack traces present per security policy?
3. **Trace spans:** which services did the request visit, and were there error spans, timeouts, or abnormal latency?
4. **Client-visible responses:** do the status/body/headers actually returned to users match expectations?

If handled exceptions must be marked as errors on the observation, Spring Framework provides interaction via `ServerRequestObservationContext`, but configure it consistently and avoid marking every 4xx response as an "unexpected exception." In real systems, distinguish client validation errors, expected business errors, and infrastructure failures.

### 7.1. Should request and response bodies be logged?

Logging full bodies can seem helpful for debugging, yet commonly introduces three classes of issues:

- **Security/privacy:** passwords, tokens, payment details, and PII can end up stored in logs or traces.
- **Performance:** large/streaming/multipart bodies make buffering content expensive in RAM, I/O, and latency.
- **Servlet semantics:** the request input stream can only be read once per lifecycle; wrapping/reading at the wrong time can break downstream processing or miss parts of the response.

If specific fields are genuinely needed for investigation, log selected structured fields, enforce length limits, and redact before output. For API auditing, define a dedicated audit mechanism with explicit policies, retention, and access control instead of treating HTTP debug logs as an official audit trail.

## 8. Testing layer by layer instead of relying on a single run

| Goal | How to test | Evidence obtained | What remains unproven |
| --- | --- | --- | --- |
| Business log on the right branch | Unit test with appender/test logger or integration test | An event was logged when the branch ran | MDC, tracer, or HTTP transport |
| Correct MVC response | `MockMvc` with appropriate context/filters | Status, headers, JSON/view, and routing | Real socket or collector |
| HTTP metrics | Live HTTP `RANDOM_PORT` + `MeterRegistry` | Timer/count and route/status tags after request | Span was exported |
| Tracing | Run tracer/collector, send request, inspect trace | Server span, trace ID, and span links | Every request is sampled |
| Propagation | App A calls App B via instrumented client | Shared trace ID, cross-service span hierarchy | Does not automatically validate every network hop |
| Production operations | Dashboards/alerts + policy checks | Trends, alerts, retention/access limits | Does not replace functional logic tests |

For latency metrics, never judge system performance from a single fast call. Account for cold start/warmup, latency distribution, traffic mix, and mocked dependencies. Histograms/percentiles depend on registry and backend configuration; configure them explicitly before setting SLOs based on p95/p99.

## 9. Common pitfalls and how to diagnose them

**Logs exist without trace IDs:** check whether a tracing bridge was added, whether the request has an active span, whether the logging pattern preserves MDC, and whether execution crossed threads without context propagation. `spring-boot-starter-actuator` alone does not guarantee tracing-based log correlation.

**Metrics exist without traces:** you may be missing a tracer/exporter, sampling may drop requests, the collector endpoint may be wrong, or the exporter may be disconnected. Metrics and tracing use separate pipelines even when derived from the same Observation.

**`http.server.requests` is missing:** verify the app actually received requests after startup, observation instrumentation/registry is configured and enabled, the `metrics` endpoint is exposed, and the meter name matches your version/convention. In non-Boot Spring Framework apps, ensure `ServerHttpObservationFilter` is registered.

**Metrics have too many distinct series:** check if tags contain raw paths, user IDs, request IDs, or query values; switch to route templates/low-cardinality tags and keep request-specific details in controlled logs/traces.

**Traces miss downstream services:** use an instrumented HTTP client builder; verify context propagation headers, each service's sampler, and that context is not lost across thread switches.

**Status 500 with exception tag `none`:** the error may have been handled by `@ExceptionHandler` or not visible to the filter as a throwable. Cross-check status and handler logs rather than assuming instrumentation is broken from a single tag.

**Low server timer while users still see slowness:** HTTP server timers generally exclude client-side DNS, TLS negotiation, proxy queues, network transit, and browser rendering. Combine metrics across client, proxy, and server.

**Observability adds overhead:** enabling 100% tracing/DEBUG or full-body logging under heavy load can hurt latency and cost. Tune sampling, tag filtering, log levels, and retention, and measure the impact before rolling out broadly.

## 10. Practical checklist

When setting up observability for Spring MVC, follow this sequence:

1. Identify the endpoints/flows to investigate along with expected statuses and latencies.
2. Enable Actuator/Observation cleanly; issue a request and verify `http.server.requests` updates.
3. Separate valuable business logs from access logs; avoid logging secrets or unnecessary bodies.
4. If traces are needed, add a tracer bridge and matching exporter; verify trace IDs in logs and server spans in the collector.
5. Use an instrumented HTTP client builder to verify a call to a second service with a shared trace ID.
6. Keep metric tags low-cardinality and use proper URI templates; configure alerts around meaningful status, throughput, and latency.
7. Verify sampling, context propagation across async boundaries, exception handling, and access controls on observation endpoints.

A system is "observable" when an initial symptom like "rising 5xx rate" lets you move from a **metric** to the relevant request/trace, and then to **logs or spans** containing explanatory evidence. That operational workflow is the criterion, not merely having three libraries in your dependencies.

### References

- Spring Framework 6.1 — Observability Support: https://docs.spring.io/spring-framework/reference/6.1/integration/observability.html
- Spring Boot 3.3 — Observability: https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html
- Spring Boot 3.3 — Metrics and the Metrics Endpoint: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html
- Spring Boot 3.3 — Tracing and Log Correlation: https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html
- Micrometer — Observation Documentation: https://docs.micrometer.io/micrometer/reference/observation/introduction.html
