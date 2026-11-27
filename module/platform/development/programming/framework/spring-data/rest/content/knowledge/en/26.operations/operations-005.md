# Observing Requests with Logs, Tracing, and Metrics in Spring Data REST

> Scope: Spring Data REST applications running on Spring MVC, with configuration examples based on Spring Boot 3.5.x. Spring Boot 4.x and other Spring Data versions may change dependencies or tag details; always use the BOM and documentation matching your project version.

## 1. Three Signals to Correlate

Observability consists of logging, metrics, and distributed tracing. Each signal answers a different question:

- **Logs** show what a request or operation did, along with human-readable diagnostic information.
- **Metrics** show how the system behaves over time: request counts, latency, error rates, throughput, and resource utilization.
- **Traces** connect the steps of the same request across filters, Spring MVC, repositories, services, and HTTP clients or message brokers.

With Spring Data REST, observe both the HTTP requests handled by the REST exporter and the underlying Spring Data repository calls. A request can succeed at the HTTP layer while being slow in a repository or an external service; relying on only one signal makes bottlenecks hard to pinpoint.

## 2. Enabling Actuator, Metrics, and Tracing

With Spring Boot 3.5, add the required dependencies. Spring Boot manages versions via dependency management; do not pin Micrometer or OpenTelemetry versions manually if the BOM already manages them.

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
    runtimeOnly("io.micrometer:micrometer-tracing-bridge-otel")
    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")
}
```

`spring-boot-starter-actuator` provides auto-configuration for Micrometer. `micrometer-registry-prometheus` exports metrics in Prometheus format; the tracing bridge and OTLP exporter connect Micrometer Observation to an OpenTelemetry Collector or OTLP receiver backend. If using Brave/Zipkin, choose the appropriate bridge and reporter per Spring Boot documentation.

Example `application.yml` for development or staging environments:

```yaml
spring:
  application:
    name: spring-data-rest-api

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus"
  tracing:
    sampling:
      probability: 1.0

logging:
  pattern:
    correlation: "[${spring.application.name:},%X{traceId:-},%X{spanId:-}] "
  include-application-name: false
```

In this example, sampling `1.0` sends 100% of traces for easier verification. By default, Spring Boot samples only 10% of requests to limit load on the trace backend; in production, choose a rate suited to your traffic, cost, and retention policies. Only expose needed endpoints. Actuator exposes only `health` over HTTP by default; protect `metrics` and `prometheus` with Spring Security, network policies, or a firewall.

Verify after starting the application:

```bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/metrics/http.server.requests
curl -i http://localhost:8080/actuator/metrics/spring.data.repository.invocations
curl -i http://localhost:8080/actuator/prometheus
```

`/actuator/metrics` uses Micrometer meter names; names normalized when exported to a backend may differ, for example Prometheus uses underscores. `/actuator/prometheus` requires the Prometheus registry and must be exposed.

## 3. Built-in Metrics for Spring Data REST

### 3.1. HTTP Request Metrics

Spring Boot automatically instruments requests passing through Spring MVC with the `http.server.requests` meter. Because Spring Data REST runs on Spring MVC, requests to collection, item, and association resources also pass through this request measurement layer. Default dimensions of the server observation include method, URI template, status, outcome, and exception/error information depending on the Spring Framework version.

Examples of questions this metric can answer:

- Is p95/p99 latency for `GET /people` increasing?
- Did the `4xx` or `5xx` rate of `POST /people` rise after a release?
- Which association endpoints have high processing times?
- How does request volume vary across instances or environments?

The URI tag should be a route template such as `/people/{id}` rather than a URL with an interpolated ID. Never create tags from raw URIs, query strings, emails, usernames, or entity IDs; each distinct value can create a new time series and cause cardinality explosion in the metrics backend.

### 3.2. Repository Invocation Metrics

Spring Boot 3.5 automatically instruments Spring Data repository method calls with the `spring.data.repository.invocations` meter. Default tags include:

| Tag | Meaning |
| --- | --- |
| `repository` | Simple name of the repository interface |
| `method` | Invoked repository method |
| `state` | `SUCCESS`, `ERROR`, `CANCELED`, or `RUNNING` |
| `exception` | Exception class name if the invocation failed |

This metric helps separate requests that are slow in HTTP handling from requests that are slow in a repository. You can annotate a repository interface or method with `@Timed` when customizing measurement; if auto-timing is already enabled for all repositories, avoid adding duplicate instrumentation. You can disable auto-timing via `management.metrics.data.repository.autotime.enabled=false` if you want to time only annotated methods.

### 3.3. Viewing and Filtering Metrics

The Actuator metrics endpoint supports filtering by tag. For example, viewing GET requests:

```bash
curl "http://localhost:8080/actuator/metrics/http.server.requests?tag=method:GET"
```

The Prometheus scrape endpoint is typically configured at `/actuator/prometheus`. Dashboards should track at a minimum request rate, error rate, p95/p99 latency, repository invocation duration, JVM, connection pools, and thread pools. Configure alerts on SLOs or meaningful operational thresholds rather than alerting on every minor fluctuation.

## 4. Attaching Trace IDs to Logs and Propagating Traces Across Services

When Micrometer Tracing is configured, Spring Boot automatically adds correlation IDs to logs. By default, the correlation ID is built from `traceId` and `spanId` in MDC. It can be customized via `logging.pattern.correlation`; the configuration example in section 2 includes the application name, trace ID, and span ID in every log line.

When calling other services, create HTTP clients from Spring Boot-provided builders so trace context is propagated automatically:

```java
@Configuration
public class HttpClientConfiguration {

    @Bean
    RestClient partnerRestClient(RestClient.Builder builder) {
        return builder
                .baseUrl("https://partner.example")
                .build();
    }
}
```

Do not instantiate `RestTemplate`, `RestClient`, or `WebClient` directly via constructors if you want auto-configured observation and trace propagation. Use `RestTemplateBuilder`, `RestClient.Builder`, or `WebClient.Builder` injected from Spring Boot.

For long-running business operations or custom measurements beyond HTTP/repository metrics, inject `ObservationRegistry` and create an observation:

```java
@Component
public class OrderOperations {

    private final ObservationRegistry observationRegistry;
    private final OrderService orderService;

    public OrderOperations(ObservationRegistry observationRegistry, OrderService orderService) {
        this.observationRegistry = observationRegistry;
        this.orderService = orderService;
    }

    public void confirm(Long orderId) {
        Observation.createNotStarted("springdatarest.order.confirm", observationRegistry)
                .lowCardinalityKeyValue("operation", "confirm")
                .observe(() -> orderService.confirm(orderId));
    }
}
```

An observation can produce both a timer metric and a span when a registry is configured. Put only bounded-value tags in `lowCardinalityKeyValue`, such as `operation`, `result`, `region`, or `entityType`. High-cardinality data such as order IDs should only be added as high-cardinality trace attributes when genuinely needed and reviewed for privacy; never use them as metric tags.

Spring Boot can enable `@Observed`, `@Timed`, and `@Counted` annotations via `management.observations.annotations.enabled=true` and `spring-boot-starter-aop`. Do not annotate controllers or repositories that are already auto-instrumented, or you will create duplicate observations.

## 5. Request Logs and Repository Event Logs

### 5.1. Structured Request Logs

Request logs should record method, route template, status, and processing duration. Avoid logging entire request/response bodies, `Authorization` headers, cookies, tokens, or personal data. A servlet filter can supplement request logging if container access logs are insufficient:

```java
@Component
public class RestRequestLogFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(RestRequestLogFilter.class);

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        long started = System.nanoTime();
        try {
            chain.doFilter(request, response);
        } finally {
            Object pattern = request.getAttribute(HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
            String route = pattern == null ? "unmatched" : pattern.toString();
            long durationMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started);
            log.info("http_request method={} route={} status={} duration_ms={}",
                    request.getMethod(), route, response.getStatus(), durationMs);
        }
    }
}
```

The filter above is an example for the servlet stack; add the corresponding servlet, `OncePerRequestFilter`, `HandlerMapping`, `Logger`, and `TimeUnit` imports. The route is read from `BEST_MATCHING_PATTERN_ATTRIBUTE` when provided by the handler; `unmatched` is used for requests that do not match a route. Test on an embedded server if you need to confirm final status codes for error dispatches or async requests. If `http.server.requests` and access logs already cover your needs, avoid adding a redundant filter.

### 5.2. Repository Event Logs

Spring Data REST publishes `BeforeCreate`, `AfterCreate`, `BeforeSave`, `AfterSave`, `BeforeLinkSave`, `AfterLinkSave`, `BeforeDelete`, and `AfterDelete` events. You can use `@RepositoryEventHandler` to record audit events by domain type:

```java
@Component
@RepositoryEventHandler
public class PersonAuditHandler {

    private static final Logger log = LoggerFactory.getLogger(PersonAuditHandler.class);

    @HandleAfterSave
    public void afterSave(Person person) {
        log.info("repository_event=after_save entity=Person id={}", person.getId());
    }
}
```

Register the handler as a Spring bean via `@Component` or `@Bean`. Event handlers are well suited for recording domain changes that went through the REST exporter; they do not replace request logs, metrics, or traces. Log the ID or operation type needed rather than serializing the entire entity. These Spring application events run synchronously by default; if moving a listener to another thread or using `@Async`, you must configure context propagation so trace IDs and MDC continue to propagate.

## 6. Context Propagation and Handled Exceptions

Trace context typically travels with the current thread. When using `@Async` or a custom executor, context can be lost across thread hops. With Spring Boot 3.5, register a `ContextPropagatingTaskDecorator` for custom executors:

```java
@Bean
ContextPropagatingTaskDecorator contextPropagatingTaskDecorator() {
    return new ContextPropagatingTaskDecorator();
}
```

For `@Async` and the auto-configured `AsyncTaskExecutor`, enable `spring.task.execution.propagate-context`; for Reactor, check `spring.reactor.context-propagation`. Do not switch event handlers to async solely to shorten request latency without first deciding how context propagation and error handling will work.

One easy-to-miss detail: HTTP server observation automatically records an exception as an error only when the exception is unhandled by the web framework and bubbles up to the servlet filter. Exceptions handled inside an `@ExceptionHandler` or converted to `ProblemDetail` may not appear in the exception/error tag even though the response returns `4xx` or `5xx`. Status and outcome still identify the response; if you also need to record handled exceptions, a custom handler can attach the exception to the observation context using `ServerHttpObservationFilter.findObservationContext(request).ifPresent(context -> context.setError(exception))`. Apply this to handlers controlled by the application and verify with tests.

## 7. Testing Observability

Test requests through MockMvc and verify meters are recorded afterward. The example below assumes `/people` is an exported collection resource and the application has a `MeterRegistry`:

```java
@SpringBootTest
@AutoConfigureMockMvc
class SpringDataRestObservabilityTest {

    @Autowired MockMvc mockMvc;
    @Autowired MeterRegistry meterRegistry;

    @Test
    void getPeopleRecordsHttpAndRepositoryMetrics() throws Exception {
        mockMvc.perform(get("/people"))
                .andExpect(status().isOk());

        Timer httpTimer = meterRegistry.find("http.server.requests")
                .tag("method", "GET")
                .tag("uri", "/people")
                .timer();
        assertThat(httpTimer).isNotNull();
        assertThat(httpTimer.count()).isGreaterThan(0);

        Timer repositoryTimer = meterRegistry.find("spring.data.repository.invocations")
                .tag("repository", "PersonRepository")
                .tag("method", "findAll")
                .timer();
        assertThat(repositoryTimer).isNotNull();
        assertThat(repositoryTimer.count()).isGreaterThan(0);
    }
}
```

Adjust `uri`, repository name, and method to match the actual endpoint; you may need test fixtures so the request actually invokes the expected repository method. Tracing tests should use a test exporter or span handler inside the test suite rather than depending on an external OTLP/Zipkin backend. Spring Boot notes that tracing reporters are not auto-configured to send data when using `@SpringBootTest`; configure a test reporter separately if you need to assert spans.

Tests should cover:

- A successful request and a `4xx`/`5xx` request, verifying count, status, and outcome.
- Repository method invocation, verifying the `spring.data.repository.invocations` meter and `state` tag.
- Custom observations wrapping business operations, verifying timers or spans are created.
- Trace IDs preserved in logs across requests and HTTP client calls; if using `@Async`, verify context propagation as well.
- Metric tags using URI templates and bounded value sets; no IDs, emails, or tokens in metric labels.
- Actuator exposing only required endpoints and denying unauthorized requests.

## 8. Troubleshooting

| Symptom | Common Cause | How to Resolve |
| --- | --- | --- |
| `/actuator/metrics` returns `404` | Endpoint not exposed or Actuator missing | Add Actuator starter and appropriate `management.endpoints.web.exposure.include` |
| `/actuator/prometheus` returns `404` | Missing Prometheus registry or endpoint not exposed | Add `micrometer-registry-prometheus`, expose `prometheus`, and check security |
| `http.server.requests` is missing | Request does not pass through instrumentation/filter or `ObservationRegistry` is inactive | Check Spring MVC stack, Actuator auto-configuration, and custom filter registration |
| `spring.data.repository.invocations` is missing | Repository invocation did not occur or auto-time is disabled | Verify the request calls a repository; check `management.metrics.data.repository.autotime.enabled` |
| Logs lack trace ID/span ID | Missing tracing bridge, sampling is 0, or log pattern overridden | Check tracing dependencies, `management.tracing.sampling.probability`, and MDC pattern |
| Trace stops at one service | HTTP client created manually or context lost across thread switches | Use auto-configured builders; configure context propagation for executors/Reactor |
| Metrics have too many time series | Tags contain raw URLs, IDs, or unbounded values | Use URI templates and low-cardinality tags; move needed data to trace attributes |
| Dashboard lacks exception tag for error responses | Exception handled by `@ExceptionHandler` before reaching servlet filter | Rely on status/outcome or set error on observation context in custom handlers |
| Same request logged multiple times | Filter, container access log, and middleware all log the same event | Pick one primary request log source; keep event logs dedicated to domain actions |

When investigating a request, search by trace ID first, read logs sharing the correlation ID, inspect the trace for per-span timing, and correlate with metrics by route/status and repository/method. This separates application bugs, slow data queries, and external dependencies.

## 9. Official References

- [Spring Boot 3.5 — Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html): logging, Micrometer Observation, low/high cardinality, and context propagation.
- [Spring Boot 3.5 — Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html): tracing bridges, OTLP, sampling, correlation IDs, trace propagation, and custom observations.
- [Spring Boot 3.5 — Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html): `http.server.requests`, `spring.data.repository.invocations`, `@Timed`, MeterRegistry, and Prometheus.
- [Spring Boot — Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint exposure, access control, and requirements for protecting operational data.
- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html): eight repository lifecycle events, annotated handlers, and bean registration.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): HTTP server observation, semantic conventions, handled exceptions, and context in event listeners.
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html): observation API and metrics/tracing model.
- [Micrometer — Prometheus](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html): registry and exporting metrics to Prometheus.