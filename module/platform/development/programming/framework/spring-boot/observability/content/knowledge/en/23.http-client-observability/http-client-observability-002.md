# RestTemplate observation

A Spring Boot application calls the Inventory service using `RestTemplate` to check stock availability. When Inventory responds slowly or returns 503, looking only at Order Service logs is usually not enough to tell which outbound request had a problem, how long it took, which host was called, and whether the error propagated from a dependency. HTTP client Observation records each outbound HTTP call as an operation with duration, outcome, and context; metrics show trends, while traces show where the dependency call sits within the overall request.

The **RestTemplate observation** lesson belongs to the **HTTP client observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; understanding context propagation, tags/cardinality, exporters, sampling, and correlating signals to investigate errors, latency, and application behavior in production environments.

> **Core point:** `RestTemplate` is only instrumented when it is configured with an appropriate `ObservationRegistry`. In Spring Boot, prefer using the `RestTemplateBuilder` provided by Boot to receive observability configuration and customizers. Creating a standalone `new RestTemplate()` can bypass that builder/customization. A client Observation describes the outbound call; a server Observation at the target service describes the inbound request. Trace context connects both sides when propagation is configured properly.

## 1. Learning Objectives

After this lesson, you can:
1. Explain `RestTemplate` observation and its place in HTTP client observability.
2. Distinguish outbound client Observation from inbound server Observation.
3. Configure `RestTemplate` via `RestTemplateBuilder` to receive `ObservationRegistry`.
4. Understand low-cardinality keys such as `clientName`, `method`, `uri`, `status`, `outcome`, and `error`.
5. Distinguish URI templates from full URLs and control metric cardinality.
6. Understand how Observation creates Micrometer metrics and tracing spans via handlers.
7. Monitor HTTP client errors, status codes, timeouts, and exceptions.
8. Understand context propagation from a server request through `RestTemplate` to a downstream service.
9. Customize `ClientRequestObservationConvention` safely.
10. Test metrics/traces and investigate when outbound calls do not appear.

## 2. What is RestTemplate observation?

`RestTemplate` is Spring Framework's synchronous HTTP client. It sends a request and waits for a response, typically via a `ClientHttpRequestFactory`. Spring Framework integrates Micrometer Observation into `RestTemplate` to record an observation for each HTTP exchange when `ObservationRegistry` is configured.

The standard Observation is typically named `http.client.requests`. An Observation can be handled by:
- `DefaultMeterObservationHandler` to create Micrometer Timer/metrics.
- Micrometer Tracing handler to create client spans.
- Other handlers if registered by the application.

An observation records the lifecycle of a client exchange: starting before sending the request and ending when the response is received or an error occurs. The convention reads the context to produce key-values, but Observation itself is not an exporter.

~~~mermaid
sequenceDiagram
    participant API as OrderController
    participant RT as RestTemplate
    participant INV as Inventory Service
    participant H as Observation handlers
    API->>RT: getForEntity(...)
    RT->>H: Start http.client.requests
    RT->>INV: HTTP request + trace context
    INV-->>RT: HTTP response
    RT->>H: Stop observation with status/timing
    RT-->>API: ResponseEntity
~~~

Client Observation and server Observation are two distinct operations:
- Client: How long did Order Service take to call Inventory and what result did it receive?
- Server: Which request did Inventory receive, how long did processing take, and what status did it return?

When trace propagation is active, the client span is typically the parent of the server span across the network boundary.

## 3. Configuring RestTemplate in Spring Boot

In Spring Boot, inject `RestTemplateBuilder` instead of instantiating standalone `RestTemplate` instances:

~~~java
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
class HttpClientConfiguration {

    @Bean
    RestTemplate inventoryRestTemplate(RestTemplateBuilder builder) {
        return builder
                .rootUri("https://inventory.internal")
                .build();
    }
}
~~~

Spring Boot can customize `RestTemplateBuilder` with components such as `ObservationRegistry`, message converters, request factory, and configured customizers. Auto-configuration details depend on dependencies and the Spring Boot version.

Using the injected bean:

~~~java
@Service
class InventoryClient {

    private final RestTemplate restTemplate;

    InventoryClient(RestTemplate inventoryRestTemplate) {
        this.restTemplate = inventoryRestTemplate;
    }

    InventoryView find(String sku) {
        return restTemplate.getForObject(
                "/api/inventory/{sku}",
                InventoryView.class,
                sku);
    }
}
~~~

Do not create a new `RestTemplate` in every method or call `new RestTemplate()` assuming it receives Spring Boot customizers. Instances created directly outside the builder may lack the application's `ObservationRegistry`, interceptors, error handlers, or timeout configuration.

### 3.1 When do you need to attach ObservationRegistry manually?

If not using the Spring Boot builder, Spring Framework allows configuring `ObservationRegistry` directly on `RestTemplate` using the corresponding version's API, for example:

~~~java
RestTemplate restTemplate = new RestTemplate();
restTemplate.setObservationRegistry(observationRegistry);
~~~

Verify that the method/API exists in the Spring Framework version in use. In Spring Boot applications, using the builder and customizers usually keeps configuration more consistent.

### 3.2 Requirements for metrics and traces

| Component | Role |
|---|---|
| RestTemplate | Creates the HTTP client Observation |
| ObservationRegistry | Orchestrates Observations and handlers |
| MeterObservationHandler | Converts Observation into Micrometer meters |
| TracingObservationHandler | Creates spans for Observations |
| MeterRegistry | Stores/exports Micrometer metrics |
| Tracer/exporter | Sends spans to the backend via the tracing pipeline |

You may see metrics without spans if `MeterObservationHandler` is present but the tracing handler/exporter is not configured. Conversely, traces may appear while the metrics registry is not yet exporting.

## 4. Client Observation Context and Convention

Spring Framework uses a dedicated context for HTTP client Observation, typically `ClientRequestObservationContext`. The context holds the request/response, request URI/template, exception, and data needed by the convention to produce `KeyValues`.

The default convention typically provides these low-cardinality keys:

| Key | Meaning | Example |
|---|---|---|
| clientName | Normalized target host/service | inventory.internal |
| method | HTTP method | GET, POST |
| uri | URI template or fallback | /api/inventory/{sku} |
| status | HTTP response status | 200, 404, 503 |
| outcome | Result category by status | SUCCESS, CLIENT_ERROR, SERVER_ERROR |
| error | Exception type or none | ResourceAccessException, none |

Exact key names and value sets depend on the Spring Framework/Micrometer convention version. Some conventions include high-cardinality values such as the full URL for use in traces; high-cardinality values should not be turned into metric tags.

### 4.1 Low-cardinality and high-cardinality

Low-cardinality values are used as dimensions for metrics. Values must come from a finite, stable set, such as HTTP method, status family, route template, or normalized client name.

High-cardinality values can differ per request, such as the full URL with query string, request ID, user ID, or token. They can be useful for specific traces/logs but are unsuitable as metric labels.

~~~text
Low cardinality:
  clientName = inventory.internal
  method = GET
  uri = /api/inventory/{sku}
  status = 200
  outcome = SUCCESS

High cardinality:
  http.url = https://inventory.internal/api/inventory/SKU-9281?debug=true
  request.id = req-8a1...
~~~

Do not use raw URLs with sensitive query parameters; do not add tokens or user input into convention values.

## 5. Why is the URI Template So Important?

`RestTemplate` supports URI templates:

~~~java
restTemplate.getForEntity(
        "https://inventory.internal/api/items/{sku}",
        InventoryView.class,
        sku);
~~~

URI templates keep the path in the form `/api/items/{sku}` so instrumentation can group requests sharing the same route. If code passes an already constructed URI:

~~~java
URI uri = URI.create(
        "https://inventory.internal/api/items/" + sku);
restTemplate.getForEntity(uri, InventoryView.class);
~~~

instrumentation may no longer know the original template. Depending on the request factory and convention, the low-cardinality `uri` may become `UNKNOWN` or another fallback; if the full URL is recorded in a high-cardinality field, it still risks containing IDs/queries. Use the overload with a URI template and variables whenever possible.

### 5.1 How does cardinality explosion affect the system?

Suppose there are 100,000 different SKUs per minute. If the `uri` metric tag contains `/items/SKU-9281`, the system could create nearly 100,000 series instead of one `/items/{sku}` series. This increases:
- RAM in the application registry and backend index.
- The number of time series to scrape/ingest.
- Storage and retention costs.
- Query time and dashboard rendering time.

URI templates are part of metric cost design.

## 6. HTTP Client Status, Outcome, and Error

Client Observation records the response status when a response is received. Outcome groups the status code. Error reflects the exception recorded by the Observation.

| Scenario | Status | Common Outcome | Possible Recorded Error |
|---|---:|---|---|
| Inventory returns OK | 200 | SUCCESS | none |
| Inventory returns Not Found | 404 | CLIENT_ERROR | none or exception depending on error handler |
| Inventory returns Too Many Requests | 429 | CLIENT_ERROR | depends on error handling |
| Inventory returns Service Unavailable | 503 | SERVER_ERROR | depends on error handling |
| DNS/connect timeout before response | UNKNOWN | UNKNOWN/fallback per convention | ResourceAccessException or specific exception |
| TLS handshake failed | No HTTP status | UNKNOWN/fallback | SSL exception |

By default, `RestTemplate` uses `DefaultResponseErrorHandler`, which typically throws an exception for 4xx/5xx after receiving the response. Therefore, `status` can be 404/503 in the Observation even though the method call ultimately throws `HttpClientErrorException`/`HttpServerErrorException`.

If the application replaces `ResponseErrorHandler` to treat 404 as a normal result, the Observation can record status 404 without an exception error. `status` and `error` are not two ways of writing the same value.

### 6.1 No response status on connection errors

If DNS lookup, TCP connect, or TLS handshake fails before receiving an HTTP response, there is no status code from the server. Instrumentation may use a fallback such as `UNKNOWN` and record the exception type. Do not fabricate a 500 status for an outbound request if the server never returned 500; distinguish transport failures from HTTP 5xx responses.

### 6.2 Retries create multiple client observations

If the application or a retry library resends a request, each attempt can create a separate client Observation/span, depending on the integration. One logical operation can consist of multiple outbound attempts. Define the metric you want to measure:
- Per attempt to see dependency load/retry volume.
- Final logical call to measure caller experience.
- Both, using distinct names and dimensions.

Do not add retry attempts into business request counts without understanding the semantics.

## 7. Trace Context Propagation via RestTemplate

When a server request has an active Observation/tracing context and `RestTemplate` is properly instrumented, the tracing integration can inject trace context into the outbound HTTP request. The downstream server extracts the context and creates a child server span.

~~~mermaid
sequenceDiagram
    participant C as External client
    participant O as Order Service
    participant R as RestTemplate
    participant I as Inventory Service
    C->>O: POST /orders
    Note over O: Server span (trace T)
    O->>R: get inventory
    Note over R: Client span (child)
    R->>I: GET /items/SKU-1 + traceparent
    Note over I: Server span (child of client)
    I-->>R: 200 OK
    R-->>O: InventoryView
    O-->>C: 201 Created
~~~

When using W3C Trace Context, outbound requests can carry `traceparent` and `baggage` if propagation is configured. The client span connects network/dependency wait time to the overall trace.

Notes:
- Having a client Observation does not guarantee a trace span; a tracing handler is required.
- Having a span does not guarantee downstream receives the parent if proxies/clients strip headers or propagation formats differ.
- If calling `RestTemplate` from a background task with no context, the trace may start independently or have no parent.
- Do not copy access tokens, session cookies, or PII into baggage; propagation context is not a place to store secrets.

## 8. Timeouts and Dependency Errors

HTTP clients need bounded timeouts. Otherwise, request threads can wait indefinitely, exhausting pools and causing cascading latency. Timeouts are part of the behavior that needs to be observed.

Request factory/timeout configuration depends on Spring Boot and the client implementation (JDK HttpClient, Apache HttpComponents, Jetty...). Illustrative example using builder customization:

~~~java
@Bean
RestTemplate inventoryRestTemplate(RestTemplateBuilder builder) {
    return builder
            .rootUri("https://inventory.internal")
            .connectTimeout(Duration.ofSeconds(2))
            .readTimeout(Duration.ofSeconds(5))
            .build();
}
~~~

Timeout properties/APIs have changed across Spring Boot versions; check the corresponding builder methods and request factory. Set a connect timeout for establishing the connection and a read/response timeout for waiting for data; do not assume one timeout covers every phase of a request.

In traces:
- A long span duration may reflect slow server processing or the client waiting on the network.
- A timeout exception may have no HTTP status.
- The downstream server may still continue processing the request after the caller times out, depending on transport/cancellation.
- Retries can create additional attempts and increase load on the dependency.

## 9. Custom ClientRequestObservationConvention

You can customize low-cardinality key-values for client Observations, for example grouping clients by dependency role. Use the convention to normalize data; do not record raw URLs, tokens, or dynamic request data into metric tags.

Example declaring the default convention:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.observation.ClientRequestObservationConvention;
import org.springframework.http.client.observation.DefaultClientRequestObservationConvention;

@Configuration
class ClientObservationConfiguration {

    @Bean
    ClientRequestObservationConvention clientObservationConvention() {
        return new DefaultClientRequestObservationConvention();
    }
}
~~~

This is an illustrative default convention configuration. For real customization, extend `DefaultClientRequestObservationConvention` or implement the interface and return finite `KeyValues`. Verify package/class APIs according to the Spring Framework version.

### 9.1 Adding dependency role

If you need to distinguish downstream services:
- inventory
- payment
- customer
- shipping

Use a normalized logical client name or a custom `dependency.role` key. Do not take the `Host` header from user requests or arbitrary URLs and attach it as a metric tag, because an attacker could generate many host values and explode cardinality.

### 9.2 Keeping standard keys for dashboard compatibility

If a custom convention drops `method`/`status`/`outcome`/`uri` or changes key meanings, dashboards, alerts, and service-level metrics can break. When changing the convention:
1. Keep standard keys unless there is a clear reason not to.
2. Add custom business keys with a small value set.
3. Version dashboard/query migrations if key semantics change.
4. Test both metrics and tracing handlers because the same convention can supply low/high-cardinality `KeyValues` to multiple signals.

## 10. RestTemplate Interceptors and Observation

`RestTemplate` has `ClientHttpRequestInterceptor`, commonly used for authentication, correlation headers, logging, or request decoration. Interceptors do not automatically replace Observation instrumentation.

An interceptor can add correlation/auth headers from the security context, log metadata, modify URIs/headers before sending, or wrap responses. Ensure the interceptor does not:
- Write full headers/bodies to logs.
- Write `Authorization`/`Cookie`/API keys to span attributes.
- Strip `traceparent`/`baggage` injected by tracing integration.
- Read the body in a way that leaves the response stream unavailable for the converter.
- Create an extra `Timer`/span duplicating the standard Observation unintentionally.

If an interceptor needs to add telemetry, use the Observation context/current Observation appropriately rather than building another HTTP client metric for the same exchange.

## 11. Observing Status and Latency in Metrics

The HTTP client `Timer` can be grouped by `clientName`, `method`, `uri`, `status`, `outcome`, and `error`. The default meter name is typically `http.client.requests`; OTel semantic conventions may use `http.client.request.duration` depending on the convention.

Conceptual query example:

~~~text
http.client.requests{
  clientName="inventory.internal",
  method="GET",
  uri="/api/items/{sku}",
  outcome="SUCCESS"
}
~~~

Use metrics to answer:
- Which dependency has high p95 latency?
- What is the 5xx/timeout rate per client?
- Which route is calling the dependency too frequently?
- How much do retries increase request volume?
- Did a specific dependency see increased latency after a deployment?

Do not use full URLs as labels. Use `clientName` and `uri` templates to keep dimensions bounded.

## 12. Linking Logs and Traces with Client Observation

Logs can include `traceId`/`spanId` to correlate with client spans. When an outbound call fails, log a short message with dependency, operation, and exception category:

~~~java
try {
    inventoryClient.find(sku);
} catch (ResourceAccessException ex) {
    log.warn("Inventory request failed dependency={} category={}",
            "inventory",
            "transport_error");
    throw ex;
}
~~~

Do not log exception messages if they may contain URLs/query tokens, credentials, or remote response bodies. If the logging framework prints stack traces automatically, verify which exception messages are permitted to be output.

In the trace backend, open the client span to inspect:
- The parent server span of the original request.
- The client operation name and peer/service.
- Method/URI/status according to the convention.
- Duration and exception events, if any.
- The downstream server span if trace context was propagated.

A single log shows the code path; a client span shows where the dependency call sits in the trace and how long it took.

## 13. Testing RestTemplate Observation

Both responses and telemetry should be tested. You can use `MockRestServiceServer` to simulate downstream HTTP without real networking.

Example test skeleton:

~~~java
@SpringBootTest
class InventoryClientObservationTest {

    @Autowired
    RestTemplate inventoryRestTemplate;

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void recordsClientRequest() {
        MockRestServiceServer server =
                MockRestServiceServer.bindTo(inventoryRestTemplate).build();

        server.expect(requestTo(
                    "https://inventory.internal/api/items/SKU-1"))
                .andRespond(withSuccess(
                    "{\"sku\":\"SKU-1\",\"available\":true}",
                    MediaType.APPLICATION_JSON));

        inventoryRestTemplate.getForObject(
                "/api/items/{sku}",
                InventoryView.class,
                "SKU-1");

        server.verify();

        Timer timer = meterRegistry.find("http.client.requests")
                .tag("method", "GET")
                .timer();

        assertThat(timer).isNotNull();
        assertThat(timer.count()).isGreaterThan(0);
    }
}
~~~

This is a test skeleton; imports, JSON fixtures, URIs, metric names, and tag keys must match the version/convention. Some mock server tests need to bind the proper request factory or use a test `ObservationRegistry` to assert `ObservationContext` directly.

### 13.1 Testing error cases

Write separate tests for HTTP 404 with the default error handler, HTTP 503 and `HttpServerErrorException`, a custom `ResponseErrorHandler` treating 404 as a normal response, connect/read timeouts, a URI template with multiple SKUs where the metric still uses one template, and trace propagation headers being injected when a current trace context exists.

### 13.2 Verifying traces end-to-end

1. Send an inbound request to Order Service.
2. Order calls Inventory via `RestTemplate`.
3. Confirm the client span is a child of the Order server span.
4. Confirm the Inventory server span uses the same Trace ID and its parent span ID is the client span.
5. Test removing propagation headers to recognize symptoms of a broken trace.

Do not only assert that any span exists; check the parent/child relationship and Trace ID.

## 14. Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| No `http.client.requests` | `RestTemplate` has no `ObservationRegistry` or does not use the configured builder | Inject `RestTemplateBuilder` or set registry directly |
| Metrics exist but no client span | Tracing handler/bridge/exporter not configured | Check Micrometer Tracing and tracing pipeline |
| Trace exists but no metrics | `MeterObservationHandler`/registry/export not active | Check Actuator, `MeterRegistry`, and registry exporter |
| Every SKU creates a metric series | Using full URI instead of URI template | Use template + URI variables overload |
| `uri=UNKNOWN` | Instrumentation did not receive template/route handler | Check URI overload and convention |
| `status=UNKNOWN` | Error before receiving HTTP response | Check DNS, connect, TLS, timeout |
| 404 throws exception | `DefaultResponseErrorHandler` treats 4xx as error | Handle exception or configure `ResponseErrorHandler` per contract |
| 503 has status and error | Server returned 5xx and client error handler threw exception | Use `status`/`outcome`/`error` to analyze |
| Client span does not link downstream | Trace context not injected/propagated or stripped | Check `ObservationRegistry`, propagation, and proxies |
| Interceptor loses `traceparent` | Interceptor replaces/deletes headers | Preserve propagation headers and test outbound requests |
| Request slow but no server span | Network/DNS/TLS or downstream not instrumented | Check client span duration and transport logs |
| Retries increase metric count | Each attempt is instrumented | Distinguish attempt metrics from logical operation metrics |
| Timeout does not stop downstream | Caller timeout does not guarantee remote work cancellation | Check transport cancellation and server behavior |
| Logs contain tokens | Interceptor logs headers or exception URL | Allowlist metadata and redact at source |

## 15. Playbook: Investigating Slow Inventory Service

**Scenario:** Order Service latency increases, but Order's HTTP server metrics do not explain the cause.

1. Filter traces by Order Service's `service.name` and the slow route.
2. Open the request's server span and find the client span to Inventory.
3. Compare client span duration with total server span duration.
4. Check method, URI template, status, outcome, and error.
5. If status is 503, open the downstream server span/logs to find the service error.
6. If status is `UNKNOWN` and error is a transport exception, check DNS, connection pool, TLS, and timeouts.
7. If the client span shows multiple attempts, check the retry policy and total wait time.
8. Compare p95/error rate metrics by `clientName`/`uri` template to determine if it is a trend or an isolated request.
9. After fixing, verify trace context connects the Order client span to the Inventory server span.

Do not conclude Inventory is slow solely from Order's total latency; the delay could be in connection setup, retries, serialization, or the network.

## 16. Self-Check Exercises

**Exercise 1 — Builder.** Why should you inject `RestTemplateBuilder` in Spring Boot instead of creating `new RestTemplate()` directly? Which components might be skipped?

**Exercise 2 — Client and server.** Distinguish between Order Service's client Observation and Inventory Service's server Observation. How do they relate in a distributed trace?

**Exercise 3 — URI template.** A service calls 10,000 different SKUs. Why is passing the URI template `/items/{sku}` better than concatenating the full URI string for metrics?

**Exercise 4 — Status and error.** `RestTemplate` receives HTTP 503 and throws `HttpServerErrorException`. How might the Observation record `status` and `error`? Why do they not contradict each other?

**Exercise 5 — Transport failure.** DNS lookup fails before receiving a response. Is there any HTTP status? What should metrics/traces express?

**Exercise 6 — Tracing.** The client span appears, but the Inventory server span does not link to the same Trace ID. List the items to check.

**Exercise 7 — Retries.** A logical call succeeds on the third attempt. Why can the client request metric increase by three? What metric is needed to measure the logical operation?

**Exercise 8 — Interceptor.** An interceptor logs all request headers for debugging. What risks can arise and how do you fix them?

### Suggested Answers

1. The builder receives Boot customizers such as `ObservationRegistry`, request factory, and other configurations; a self-created instance may not be instrumented.
2. Client Observation measures the outbound exchange; server Observation measures the inbound request. The client span is usually the parent of the server span when context is injected/extracted.
3. URI templates keep tag cardinality low; raw URIs create series per SKU.
4. Status 503 describes the response; `error` can be `HttpServerErrorException` thrown by the default handler. The two fields describe two different aspects.
5. There is no HTTP response status. Record the transport exception and an appropriate fallback status/outcome such as `UNKNOWN` per convention.
6. Check `ObservationRegistry`/tracing handler, propagation format, `traceparent` header, proxies/interceptors, and server extraction.
7. Each attempt is a separate HTTP exchange. Add a business timer/counter around the logical call if you need to measure logical call count and end-to-end duration.
8. Headers may contain `Authorization`/`Cookie`/API keys. Allowlist safe headers or log normalized method/route/status.

## 17. Official References

- [Spring Framework — RestTemplate](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestTemplate` API, request factories, interceptors, and client configuration.
- [Spring Framework — HTTP Client Observability](https://docs.spring.io/spring-framework/reference/integration/observability.html): client observations, `ClientRequestObservationContext`, and convention keys.
- [Spring Boot — Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): `RestTemplateBuilder` and auto-configured client builders.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): HTTP client metrics, tags, and customization.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation lifecycle, handlers, conventions, and context.
- [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/): tracing bridge, span lifecycle, and propagation.
- [OpenTelemetry Semantic Conventions — HTTP](https://opentelemetry.io/docs/specs/semconv/http/): HTTP client attributes, status, and error semantics.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): propagation across process/network boundaries.
- [Spring Framework — RestTemplate API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/client/RestTemplate.html): API and `ObservationRegistry` configuration.

**Remember:** `RestTemplate` observation records each outbound HTTP exchange. Use `RestTemplateBuilder` to receive `ObservationRegistry` and Boot customizers; use URI templates to keep metric cardinality low; read `status`, `outcome`, and `error` as separate fields. Observation handlers determine which metrics/traces are created, while tracing propagation connects the client span with the downstream server span. When a dependency is slow or failing, open the client span to separate network/timeout/retry time from business processing and verify the full trace context.
