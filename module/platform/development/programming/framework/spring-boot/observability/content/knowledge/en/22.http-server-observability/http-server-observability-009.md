# Servlet Instrumentation in Spring Boot

In a Spring Boot application running on the Servlet stack, every HTTP request passes through the container, filter chain, Spring Security, `DispatcherServlet`, controller, and business layers. To know which requests are slow, where errors are returned, or which dependencies are invoked, you must observe requests at the HTTP server boundary. **Servlet instrumentation** creates an observation context for the request/response lifecycle, records essential HTTP characteristics, and links spans/logs with processing inside the application.

In the **SPRING_BOOT_OBSERVABILITY** module, Servlet instrumentation is part of HTTP server observability alongside Micrometer Observation, metrics, logs, and distributed tracing. This lesson belongs to the **HTTP server observability** chapter and focuses on **Servlet instrumentation**: how Spring Boot automatically observes requests, the role of Servlet Filters and Observation conventions, how to safely add business metadata, handling async/error dispatches, controlling cardinality, testing, and troubleshooting inaccurate HTTP server telemetry.

## Learning Objectives

After this lesson, you will be able to:

1. Describe the HTTP request lifecycle in a Servlet container and where instrumentation sits.
2. Explain the relationship between Servlet Filters, Micrometer Observation, metrics, and tracing.
3. Identify auto-instrumentation provided by Spring Boot and avoid creating duplicate instrumentation.
4. Read common HTTP server metrics such as request count and duration by route/status.
5. Understand how server trace spans link to client trace context.
6. Add custom Observation or filter metadata without altering HTTP semantics.
7. Handle async dispatches, error dispatches, security chains, and context cleanup.
8. Control route cardinality, sensitive data, and log correlation.
9. Write tests across Observation, `MockMvc`, and embedded servlet container layers.

## 1. What Is Servlet Instrumentation?

Servlet instrumentation attaches measurement and tracing capabilities to the Servlet API request lifecycle. Instrumentation can be implemented by filters, interceptors, or specialized framework/container integrations. In Spring Boot, HTTP server instrumentation is typically auto-configured when an application uses the Spring MVC/Servlet stack and appropriate observability dependencies.

An HTTP server observation typically starts when a request enters the server boundary and ends when the response completes. During that span of time, the system can capture HTTP method, route template, response status, processing duration, exceptions/errors, trace context, and Resource identity.

### 1.1. Position in the Servlet Request Lifecycle

~~~mermaid
flowchart TD
    Client["HTTP client"] --> Container["Servlet container"]
    Container --> Filters["Servlet Filter chain"]
    Filters --> Security["Spring Security filters"]
    Security --> Dispatcher["DispatcherServlet"]
    Dispatcher --> Handler["HandlerMapping / Controller"]
    Handler --> Service["Application service"]
    Service --> Response["Build response"]
    Response --> Dispatcher
    Dispatcher --> Security
    Security --> Filters
    Filters --> Container
    Container --> Client
    Filters -. "Observation / server span" .-> Telemetry["Metrics / traces / logs"]
~~~

The exact position of the tracing filter and security filters depends on auto-configuration and filter ordering. To observe the entire request, ensure instrumentation sits at the proper boundary and is not registered twice.

### 1.2. Filter, `HandlerInterceptor`, and Observation

| Mechanism | Scope | When to Use |
| --- | --- | --- |
| Servlet Filter | Servlet request/response and filter chain | Cross-cutting concerns at the server boundary |
| Spring MVC `HandlerInterceptor` | Before/after controller handler | Metadata tied to an already-routed handler |
| Micrometer Observation | Unified observability model | Lifecycle, context, and handlers for metrics/tracing |
| Container instrumentation | Tight container/runtime integration | Container-level observation if provided by the platform |

A Filter sees the request before a handler is selected. A `HandlerInterceptor` can read the mapped handler/route, but applies only within Spring MVC. Observation is an abstraction for lifecycle and handlers; it is not synonymous with one specific filter type.

## 2. Spring Boot Auto-Instrumenting the HTTP Server

In a Spring Boot Servlet application, appropriate observability and tracing dependencies enable auto-configuration to attach instrumentation to the request lifecycle. When Actuator/Micrometer Observation is enabled, Spring MVC server requests can be observed and produce metrics; when a Micrometer Tracing bridge is added, eligible observations can create spans.

Illustrative dependencies for Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.micrometer:micrometer-observation-test'
}
~~~

Keep versions managed by the Spring Boot BOM. Do not pin individual Micrometer/OpenTelemetry versions when the BOM manages them; check compatibility before upgrading.

### 2.1. Observation and the Tracing Bridge

Micrometer Observation provides an API representing an observed operation. An Observation has a start/stop lifecycle, a context carrying metadata, and handlers that can turn the observation into metrics or tracing.

For an HTTP server request:

1. Instrumentation detects the request starting.
2. Creates the corresponding Observation/context.
3. Captures method and initial metadata.
4. Once the route is resolved, the convention can attach the route template.
5. When the response finishes, instrumentation captures status, outcome, and duration.
6. Observation handlers update meters and/or tracing spans per configuration.

An Observation does not guarantee both metrics and traces are produced. The outcome depends on handlers, registries, tracing bridges, samplers, and exporters.

### 2.2. Metrics and Tracing Have Different Lifecycles

- HTTP server metrics aggregate many requests into counters/timers/histograms.
- A server span represents a single request or processing segment within a trace.
- Log events emitted during processing can carry `traceId`/`spanId` via MDC.
- Exporters send spans to a Collector/backend; a separate registry or exporter sends metrics to their destination.

Never use sampled span counts as a substitute for request counts from metrics.

### 2.3. Server Resource Identity

Every Spring Boot instance needs a stable Resource identity such as `service.name`, `service.version`, environment, and instance ID. Resource answers which service emitted the telemetry; route/method/status are request attributes. Never put request IDs, user IDs, or raw URLs into Resource.

## 3. HTTP Server Metrics: Request Count and Duration

Spring Boot/Micrometer can emit HTTP server measurements. Exact meter names and tags depend on the Spring Boot/Micrometer version and registry. In common Spring Boot versions, the HTTP server meter is typically named `http.server.requests`; inspect the actual meter via Actuator or the registry rather than assuming a fixed schema.

Commonly useful dimensions:

| Dimension | Example | Cardinality |
| --- | --- | --- |
| `method` | `GET`, `POST` | Low |
| `uri`/`route` | `/orders/{orderId}` | Should be a route template |
| `status` | `200`, `404`, `500` | Low |
| `outcome` | `SUCCESS`, `CLIENT_ERROR`, `SERVER_ERROR` | Low |
| `exception` | Exception name or `NONE` | Must be bounded |
| `application`/`service` | `order-service` | Finite set of services |

### 3.1. Route Template Instead of Raw URI

Do not record metric tags using raw paths such as:

~~~text
/orders/10001
/orders/10002
/orders/10003
~~~

If every order ID becomes a tag value, every request can create a new time series. Use a stable route template:

~~~text
/orders/{orderId}
~~~

A route template represents the logical endpoint and keeps cardinality manageable. Before a route is resolved, instrumentation may use a placeholder or another route value; inspect actual output on your framework/version.

### 3.2. Prometheus Query Examples

Request rate from histogram/count series, depending on exposed metric names:

~~~promql
sum by (uri, method) (
  rate(http_server_requests_seconds_count[5m])
)
~~~

HTTP 5xx ratio:

~~~promql
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
~~~

p95 latency with classic histograms:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

These examples assume the registry exposes histogram metrics with the matching names/labels. Names like `uri`, `status`, `method`, the `_seconds` suffix, and bucket availability may differ by version or configuration. Inspect actual scrape output and adjust queries accordingly.

### 3.3. Histograms and Percentiles

If p95/p99 are needed in Prometheus, histograms must be enabled/configured properly. A Timer may export count/sum; percentile histograms or SLO boundaries must be enabled via meter distribution configuration. Client-side percentiles are not the same as server-side histogram quantiles: check your backend and how aggregation works across multiple instances.

## 4. Tracing Server Spans and Trace Context

When a request enters Spring Boot, server instrumentation can extract context from incoming headers such as W3C `traceparent`, continue an existing trace if the context is valid, start a new trace if there is no remote parent, create a server span wrapping request handling, make the span active in the execution scope, and end the span when the request completes.

W3C header example:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

`traceparent` carries Trace ID, Parent ID, and trace flags. Baggage is a separate header carrying controlled metadata pairs; never use baggage in place of authentication or authorization.

### 4.1. Server Span and Downstream Client Spans

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as order-service
    participant Inventory as inventory-service
    participant Collector
    Client->>Order: POST /orders + traceparent
    Note over Order: SERVER span A
    Order->>Inventory: HTTP request + child context
    Note over Inventory: SERVER span C
    Inventory-->>Order: Response
    Order-->>Client: HTTP 201
    Order->>Collector: Export order spans
    Inventory->>Collector: Export inventory spans
~~~

The Trace ID is shared across services. Each service emits spans with its own Resource identity. HTTP client instrumentation in `order-service` creates a client span; server instrumentation in `inventory-service` creates a server span with the proper parent relationship.

### 4.2. Sampling

Head-based samplers decide early whether a trace will be recorded/exported. If a trace is dropped at the start, an error at the end of the request cannot retroactively cause the SDK to emit the dropped spans. Tail sampling in the Collector can prioritize errors or high latency if the SDK sends full data to the Collector and trace-ID-based routing is guaranteed.

HTTP metrics must still record all requests per instrumentation even when traces are sampled. Use metrics for request rates, error ratios, and SLOs; use trace samples for investigation.

## 5. Adding Metadata with `ObservationConvention`

When default instrumentation does not supply necessary business metadata, you can use `ObservationConvention` or a custom `Observation`. Prefer existing conventions and Spring Boot/Micrometer extension points before writing a custom filter to create spans.

Custom business Observation example:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final ObservationRegistry observationRegistry;

    public OrderService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public void createOrder() {
        Observation.createNotStarted("orders.create", observationRegistry)
                .lowCardinalityKeyValue("orders.channel", "web")
                .observe(() -> {
                    reserveInventory();
                    authorizePayment();
                });
    }

    private void reserveInventory() {
        // Call inventory dependency.
    }

    private void authorizePayment() {
        // Call payment dependency.
    }
}
~~~

This is a custom business observation inside an HTTP server request. It does not replace server instrumentation and should not create a duplicate server span. Add only low-cardinality keys with small value sets; never put order ID, email, or raw URL into low-cardinality tags.

### 5.1. Low-Cardinality and High-Cardinality

Micrometer Observation distinguishes low-cardinality key-values (which can be used by metrics and tracing handlers) from high-cardinality key-values (better suited for span metadata if needed, not metric labels). Even when a high-cardinality key does not become a metric label, it can still increase indexing cost or leak data. Require privacy reviews and size limits.

### 5.2. Meaningful Operation Naming

Observation names should be stable and describe the operation, such as `orders.create` or `inventory.reserve`. Never embed IDs in observation names like `orders.create.10001`. Use route templates/operation names for aggregation and searching.

## 6. When Should You Write a Custom Servlet Filter?

Spring Boot typically already provides HTTP server instrumentation when appropriate dependencies/configurations are present. Writing a custom filter just to create an extra server span usually results in two spans wrapping the same request, double-counted request metrics, inconsistent route/status/duration, duplicate trace correlation, and broken security/async ordering.

Before writing a filter, check whether the requirement can be solved with:
1. An existing `ObservationConvention` or extension point.
2. A custom business `Observation`.
3. A `HandlerInterceptor` if metadata is needed after MVC selects a handler.
4. A dedicated filter only for metadata/cross-cutting behavior that genuinely lacks an appropriate extension point.

### 6.1. Filter Example for Non-Sensitive Metadata

If you need to record an authenticated channel header, a filter can set a separate business context field. Illustrative example:

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.Locale;
import java.util.Set;

@Component
public class OrderChannelLoggingFilter extends OncePerRequestFilter {
    private static final Set<String> ALLOWED =
            Set.of("web", "partner", "batch");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {

        String candidate = request.getHeader("X-Order-Channel");
        String channel = candidate == null
                ? "unknown"
                : candidate.trim().toLowerCase(Locale.ROOT);

        if (!ALLOWED.contains(channel)) {
            channel = "unknown";
        }

        String previous = MDC.get("orders.channel");
        try {
            MDC.put("orders.channel", channel);
            filterChain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.remove("orders.channel");
            } else {
                MDC.put("orders.channel", previous);
            }
        }
    }
}
~~~

This example illustrates a bounded allowlist and cleanup. In production, the channel must come from a verified trusted source; if callers can set the header arbitrarily, never treat it as proof of partner type or authorization. If metadata was already set in another scope, save and restore the previous value rather than unconditionally removing it.

### 6.2. `OncePerRequestFilter` and Dispatcher Types

Servlets have dispatcher types `REQUEST`, `ASYNC`, `ERROR`, `FORWARD`, and `INCLUDE`. `OncePerRequestFilter` provides hooks to decide whether to skip async/error dispatches; default behavior and registration depend on the Spring version. A custom filter may run on `REQUEST` dispatch yet skip `ASYNC` or `ERROR` dispatches depending on configuration.

Do not use a custom filter to mimic a full span lifecycle unless dispatcher types and async completion are handled accurately.

## 7. Async Servlet Requests and Request Lifecycles

Servlet async lets the container release the initial request thread while the response is still being processed. The request lifecycle can span multiple threads and dispatches. If instrumentation ends the span when the initial thread exits the filter chain, duration will be wrong or context will close prematurely.

~~~mermaid
sequenceDiagram
    participant Container
    participant Filter
    participant Controller
    participant Worker
    participant Client
    Container->>Filter: REQUEST dispatch
    Filter->>Controller: doFilter
    Controller->>Container: startAsync()
    Container-->>Filter: Initial thread returns
    Container->>Worker: Execute async work
    Worker->>Container: Complete / dispatch
    Container->>Filter: ASYNC dispatch or completion callback
    Filter-->>Container: Finish lifecycle
    Container-->>Client: Response completed
~~~

Instrumentation must integrate with the Servlet async lifecycle so the server span covers the full request/response duration. Never leave MDC/`ThreadLocal` on the old thread and assume async workers will see it. Use proper context propagation and test against an embedded container.

### 7.1. Error Dispatch

When a controller throws an exception, a Spring exception resolver or container error dispatch may handle the response. Instrumentation must distinguish handled exceptions from true request failures and final statuses. Do not create a second server span on an `ERROR` dispatch if the request already has a primary span, unless intentionally designed that way.

### 7.2. Timeouts and Cancellation

Request timeouts/cancellations can finish through a different lifecycle than normal responses. Observe status, exceptions, and duration from real requests. Test server timeouts, client disconnects, and cancelled async operations if your application includes these cases.

## 8. Filter Ordering, Spring Security, and Route Mapping

Filter order determines what instrumentation sees:

- A filter before security can observe requests rejected by authentication/authorization.
- A filter after security may only see requests that passed certain security checks.
- A filter close to `DispatcherServlet` can more easily read the resolved route/handler, yet it does not cover requests outside MVC.
- Error/async dispatches require proper filter registration.

Do not change filter ordering just to add correlation without understanding security behavior. Tracing instrumentation must never expose tokens, session cookies, or principal details in span/log attributes.

### 8.1. Never Log Authorization or Cookies

Request headers often contain credentials. Never copy all headers into Observation, span attributes, or MDC. If authentication outcomes must be recorded, use finite categories such as `authenticated`, `anonymous`, `rejected`; never record raw identities/tokens.

### 8.2. Route Templates and Exception Mapping

The route tag should be a route template such as `/orders/{orderId}`, not a raw path. Exception tags must be controlled; class names can be useful, while messages often contain sensitive data or dynamic values. The final status must match the actual response after exception handling.

## 9. Cardinality and Data in HTTP Server Telemetry

| Value | Should It Be a Metric Tag? | Reason |
| --- | --- | --- |
| HTTP method | Yes | Small set |
| Route template | Yes, if normalized | Finite endpoints |
| Status code/outcome | Yes | Finite value set |
| Service name | Yes, per metric model | Stable |
| Raw URL/query string | No | Variable and may contain PII |
| Request ID/Trace ID | No | Nearly unique per request |
| User/customer ID | No | High cardinality and sensitive |
| Exception message | No | Free-form, easily leaks data |
| Remote IP | Not by default | Cardinality/privacy/security |
| Raw user agent | Not by default | Diverse and long |

Span attributes can still bloat OTLP payloads if headers, query strings, or bodies are stored. Record only necessary fields, enforce size limits, and redact data. Never confuse "not a metric label" with "zero cost."

### 9.1. Correlation IDs in Logs

Trace ID/span ID can be populated into MDC while a server span is active. Logging patterns/structured encoders must output the right keys. MDC does not replace server instrumentation, and a log containing a trace ID does not prove the trace was successfully sampled/exported.

## 10. Testing Servlet Instrumentation

Test both metrics/Observation behavior and trace propagation. Each layer proves something different.

| Test Type | Used to Verify | Limitations |
| --- | --- | --- |
| Observation unit test | Custom Observation name, tags, and lifecycle | Does not run a servlet container |
| `MockMvc` test | MVC routing, filters/interceptors, and responses | Does not fully simulate embedded container/async |
| Embedded server integration test | Servlet filters, statuses, async dispatches, and real instrumentation | Slower |
| Tracing exporter test | Span IDs, parent relationships, Resource | Does not necessarily test full networking |
| OTLP smoke test | Export to Collector/backend | Requires a test Collector or mock receiver |

### 10.1. Testing Custom Observations

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class OrderObservationTest {
    @Test
    void recordsOrderOperation() {
        TestObservationRegistry registry = TestObservationRegistry.create();

        Observation.createNotStarted("orders.create", registry)
                .lowCardinalityKeyValue("orders.channel", "web")
                .observe(() -> { });

        assertThat(registry.getCompletedObservationContexts()).hasSize(1);
    }
}
~~~

This example tests basic lifecycle behavior; exact assertion APIs may vary by Micrometer version. It does not prove that the HTTP server filter or OTLP exporter works.

### 10.2. `MockMvc` and Embedded Server

`MockMvc` can verify controller responses, statuses, and routes, but it does not go through the same embedded Tomcat/Jetty/Undertow lifecycle as a socket-level request. When testing Servlet container instrumentation, use integration tests with an embedded server.

A `SpringBootTest` with `RANDOM_PORT` can:
1. Send an HTTP request to the embedded server.
2. Retrieve HTTP server meters from `MeterRegistry`.
3. Verify the meter count increments.
4. Send a request with an incoming `traceparent`.
5. Verify the server span preserves the Trace ID and proper parent relationship.
6. Send an error request and verify status/exception semantics.
7. Send an async request if the app uses Servlet async; verify the span only ends after the response completes.
8. Verify MDC correlation in log events if a test logging appender is configured.

Do not hard-code IDs since they are generated dynamically. Assert relationships and presence.

### 10.3. Cardinality Regression Testing

Send multiple requests with different order IDs to the same route. Verify the meter still uses the `/orders/{orderId}` route template rather than creating a tag value per raw path. This test prevents filter/convention changes from inflating time series.

## 11. Troubleshooting Servlet Instrumentation

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| No HTTP server meter | Missing Actuator/Observation handler or instrumentation disabled | Check dependencies, `MeterRegistry`, and actual meters |
| Meter exists but URI is `UNKNOWN` | Route unresolved or request outside MVC mapping | Check route mappings and conventions |
| Every order ID creates a series | Raw URI used as a tag | Use route templates, remove dynamic paths |
| HTTP metrics double-counted | Custom filter/Observation duplicates auto-instrumentation | Check filter beans and handler registration |
| No server span | Tracing bridge/sampler/instrumentation inactive | Check active tracer and sampling |
| Trace ID not linked from client | Wrong propagator/header/context extraction | Inspect `traceparent` |
| Span ends too early in async | Filter lifecycle does not follow async completion | Test embedded container and async dispatches |
| Error response lacks expected status | Exception resolver/container error dispatch alters response | Check final status and error handling |
| Logs missing `traceId`/`spanId` | MDC integration/pattern not working | Check MDC and encoder |
| MDC leaks across requests | Custom filter fails to restore/clear context | Check `finally` and test thread reuse |
| Collector receives no traces | Wrong exporter endpoint/network/auth | Check OTLP config and receiver |
| Filter does not run on `ERROR` dispatch | Dispatcher type/`OncePerRequestFilter` hook | Check filter registration and skip logic |
| 401 requests have no trace | Filter order/instrumentation placed after security | Check filter chain and security ordering |

### 11.1. Investigation Workflow

1. Confirm requests actually hit the embedded servlet container.
2. Verify Actuator, `ObservationRegistry`, and `MeterRegistry` are configured.
3. Inspect the actual HTTP server meter and tag values.
4. Check the tracing bridge, active span, and sampling decision.
5. Cross-check the server span with the incoming `traceparent`.
6. Check filter ordering, async/error dispatches, and exception handling.
7. Verify exporter/Collector if spans are created yet absent from the backend.
8. Inspect logs after the encoder/appender to confirm MDC fields are actually emitted.

Do not add a second filter that creates a server span before checking what auto-configuration is already doing.

## 12. Production Checklist

| Criterion | Required Evidence |
| --- | --- |
| Servlet stack identified | Spring MVC and embedded container configured |
| HTTP server Observation active | Request lifecycle recorded once |
| Metric tags low-cardinality | Normalized route template, method, status/outcome |
| Server span created properly | Valid Trace ID, span kind, and status |
| Propagation tested | Incoming `traceparent` links accurately |
| Resource identity accurate | `service.name`/version/environment set per instance |
| Async/error dispatches verified | Span ends per response lifecycle |
| Intentional filter ordering | Security and instrumentation do not mask each other |
| No duplicate instrumentation | Meter/span counts are not doubled |
| No sensitive data exported | Headers/body/tokens/PII filtered out |
| MDC cleaned up | No leaked context from previous requests |
| Export pipeline monitored | Queues, exporter errors, Collector drops |
| Metric SLIs independent of sampling | Request count/error rate never derived from traces |
| Multi-layer regression tests | Observation, MVC, embedded server, and cardinality |

## 13. Lab: Instrumenting the `order-service` Servlet Stack

**Context:** `order-service` uses Spring MVC on a Servlet container, exposes `POST /orders/{orderId}`, and calls `inventory-service`. The operations team needs HTTP metrics, server spans, and logs with trace/span IDs. A custom filter currently adds request metadata.

**Tasks:**

1. Enable Actuator and a Micrometer Tracing bridge compatible with the Spring Boot BOM.
2. Verify HTTP server instrumentation creates Observations/metrics and server spans.
3. Send multiple requests with different order IDs; prove meters use only the route template, not raw URIs.
4. Send a request with `traceparent` from a test client; verify Trace ID/Parent ID and server span.
5. Create a business Observation `orders.create` with the low-cardinality tag `orders.channel`.
6. Audit the custom filter: retain only verified metadata, avoid duplicate spans/metrics, and restore MDC in `finally`.
7. Send requests through Spring Security; verify 200 and 401/403 per filter ordering.
8. Add an async endpoint/Servlet operation if the app uses async; verify the server span ends after response completion.
9. Trigger 4xx and 5xx errors; verify final status, span status, and metric outcome.
10. Capture logs and verify `traceId`/`spanId` accuracy across controller/service/client spans.
11. Run cardinality tests with many order IDs and thread reuse to catch context leaks.
12. Write a runbook for cases where metrics exist but traces are missing, meters double-count, or URI tags grow unexpectedly.

**Expected deliverables:** dependency configuration, evidence of HTTP server Observations/metrics/traces, controlled custom convention/filter, tests across MVC and embedded server, and an operational runbook.

## 14. Key Takeaways

**Servlet instrumentation** observes HTTP requests at the Servlet server boundary and connects that lifecycle to metrics/tracing. Spring Boot/Micrometer can automatically provide HTTP server Observations when dependencies and configuration are in place; custom Filters should only add missing behavior and must avoid double-counting or duplicating spans.

Route templates, method, and status are useful dimensions for HTTP metrics; raw URLs, request IDs, user IDs, and exception messages do not belong in metric tags. Incoming `traceparent` connects the server span to an external trace; Resource identifies the service emitting telemetry; MDC attaches `traceId`/`spanId` to log events. Async/error dispatches, filter ordering, context cleanup, privacy, and cardinality must be tested using an embedded servlet container. Use metrics as the source for SLIs, traces for investigation, and logs for contextual event details.

**References:**
- [Spring Boot — HTTP Server Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer Observation — Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Framework — Servlet Filters](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
- [Jakarta Servlet Specification](https://jakarta.ee/specifications/servlet/)
- [OpenTelemetry — HTTP Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/http/)
