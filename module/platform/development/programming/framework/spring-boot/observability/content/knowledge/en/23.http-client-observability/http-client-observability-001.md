# http.client.requests

In the **HTTP client observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module, `http.client.requests` is the standard Observation/Meter name that Spring Framework and Micrometer use to record outbound HTTP call activity. Observations help Spring Boot applications measure the duration of external service calls, track status/outcome, and create client spans when tracing is enabled. As a result, operations teams can identify which dependency is slow, whether client error rates are rising, or if requests are timing out before the impact spreads.

HTTP client observability only works properly when the client is created and configured in a way that integrates Observation. Not every HTTP call is measured automatically: self-instantiated clients, builders without an `ObservationRegistry`, or libraries lacking instrumentation can bypass the pipeline. This lesson explains how `http.client.requests` works with Spring Boot, Micrometer Observation, commonly used HTTP clients, tags, tracing context, testing, and troubleshooting.

## 1. Learning Objectives

After this lesson, you can:

1. Explain the role of `http.client.requests` in HTTP client observability.
2. Distinguish between client Observation, metrics timer, and client span.
3. Identify common tags such as `method`, `uri`, `status`, `outcome`, and `exception`.
4. Configure `RestTemplate`, `RestClient`, and `WebClient` to use `ObservationRegistry`.
5. Understand why custom clients/builders can lose default instrumentation.
6. Control URI templates and the cardinality of outbound request metrics.
7. Link client spans with server spans via trace context propagation.
8. Distinguish between HTTP error responses, exceptions, timeouts, and retries.
9. Inspect metrics via Actuator and the metrics backend.
10. Write integration tests to verify that observations are created properly and do not leak sensitive data.

## 2. What is http.client.requests?

`http.client.requests` is the Observation name commonly used for an HTTP client exchange instrumented by Spring Framework. When the client performs a request, the instrumentation creates an Observation around the lifecycle of sending the request and receiving the response. An Observation can be processed by multiple handlers:

- The Micrometer metrics handler records timers and tags.
- The Micrometer Tracing handler creates client spans.
- Other Observation handlers can add logging or conventions.

An HTTP client Observation helps answer: which dependency is being called and with which HTTP method; how long the request took; which category the response status belongs to; whether the error occurred during DNS/connect/TLS/read or during processing; and whether the downstream request is connected to the current trace.

| Component | Purpose | Example |
| --- | --- | --- |
| HTTP client Observation | Describes an HTTP exchange at the instrumentation level. | http.client.requests |
| Timer metric | Aggregates call count and duration. | Count, total time, max, histogram. |
| Client span | Represents an outbound call in a distributed trace. | GET inventory-service /items/{id} |
| Log record | Records a specific event or error. | Timeout when calling inventory. |

Observation is the common integration point. Metrics and tracing are different representations of the same activity; they do not necessarily share the same tags or retention. Meter names may be converted by the backend upon export; for example, Prometheus timer series have `_seconds_count`, `_seconds_sum`, and histogram buckets suffixes. Verify the naming convention of the registry in use.

## 3. Lifecycle of an HTTP Client Observation

~~~mermaid
sequenceDiagram
    participant App as Spring Boot service
    participant Client as Instrumented HTTP client
    participant Registry as ObservationRegistry
    participant Handler as Observation handlers
    participant Remote as Downstream service

    App->>Client: Send HTTP request
    Client->>Registry: Start http.client.requests
    Registry->>Handler: Start metrics/tracing
    Client->>Remote: HTTP request + trace context
    Remote-->>Client: HTTP response
    Client->>Registry: Stop Observation
    Registry->>Handler: Record duration/status/span
    Client-->>App: Return response or exception
~~~

The Observation typically starts when the client performs the exchange and ends when it receives a response or encounters an error. The recorded duration depends on the implementation/instrumentation and includes waiting for the response within the measured lifecycle.

The client span is usually a child of the current span if context propagation works. If there is no current span, the client instrumentation may create a root span or lack the expected parent relationship depending on the context.

Do not manually create an Observation with the same name around a client call if the client already instruments itself; doing so can create duplicate timers/spans. If you want to measure a larger business operation, create an Observation with a separate name wrapping the operation and let the HTTP client Observation describe the inner dependency exchange.

## 4. Supported HTTP Clients

Spring Framework provides instrumentation for several common HTTP client abstractions. Spring Boot auto-configuration can provide a builder/bean already integrated with Observation when dependencies and configuration are appropriate.

| Client | Common integration approach | Points to note |
| --- | --- | --- |
| RestTemplate | `RestTemplateBuilder` and appropriate observation registry/interceptors. | Create from Boot builder to receive customizers. |
| RestClient | `RestClient.Builder` configured by Boot. | Use the injected builder; do not create a standalone builder if auto-configuration is needed. |
| WebClient | `WebClient.Builder` with `ObservationRegistry`. | Use the reactive client builder configured by Boot. |
| Java HttpClient/Apache/OkHttp | Depends on the library and corresponding instrumentation. | Does not automatically have Micrometer Observation just because Actuator is present. |

API names and auto-configuration depend on the Spring Boot/Spring Framework version. `RestClient` is available in newer Spring Framework lines; older applications may only use `RestTemplate` or `WebClient`.

## 5. Configuring RestTemplate

In Spring Boot, inject `RestTemplateBuilder` and create the client from the builder:

~~~java
@Service
public class InventoryClient {
    private final RestTemplate restTemplate;

    public InventoryClient(RestTemplateBuilder builder) {
        this.restTemplate = builder
                .rootUri("http://inventory-service")
                .build();
    }

    public InventoryResponse findItem(String itemId) {
        return restTemplate.getForObject(
                "/items/{itemId}",
                InventoryResponse.class,
                itemId);
    }
}
~~~

The Boot builder can apply customizers, message converters, and configured observation customization. If you manually instantiate `new RestTemplate()` or replace the request factory/interceptors improperly, you may bypass the integrated configuration.

Example bean using the builder:

~~~java
@Configuration(proxyBeanMethods = false)
class HttpClientConfiguration {
    @Bean
    RestTemplate inventoryRestTemplate(RestTemplateBuilder builder) {
        return builder.rootUri("http://inventory-service").build();
    }
}
~~~

Do not create multiple `RestTemplate` instances unnecessarily inside every method. Reuse a configured client with an appropriate connection pool and timeout.

## 6. Configuring RestClient

`RestClient` is the synchronous fluent HTTP client in Spring Framework. Spring Boot can provide a customized `RestClient.Builder`:

~~~java
@Service
public class PricingClient {
    private final RestClient restClient;

    public PricingClient(RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("http://pricing-service")
                .build();
    }

    public PriceResponse getPrice(String sku) {
        return restClient.get()
                .uri("/prices/{sku}", sku)
                .retrieve()
                .body(PriceResponse.class);
    }
}
~~~

Use the injected builder to retain the customizers and `ObservationRegistry` configured by Boot. If you call a standalone factory/builder directly, you need to attach `ObservationRegistry` manually according to the API of the Spring Framework version in use.

## 7. Configuring WebClient

`WebClient` is the reactive HTTP client. Spring Boot can provide a `WebClient.Builder` already configured with `ObservationRegistry`:

~~~java
@Service
public class CatalogClient {
    private final WebClient webClient;

    public CatalogClient(WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("http://catalog-service")
                .build();
    }

    public Mono<ProductResponse> getProduct(String productId) {
        return webClient.get()
                .uri("/products/{productId}", productId)
                .retrieve()
                .bodyToMono(ProductResponse.class);
    }
}
~~~

Using the injected builder preserves customizers, connectors, and Observation configuration managed by Boot. Reactive pipelines can run across multiple threads; trace context must be propagated through the Reactor context and corresponding instrumentation. Do not manually read MDC on one thread and assume every callback will see that value.

If creating a `WebClient` with a standalone builder, attach `ObservationRegistry` properly and verify context propagation. Avoid creating manual Observations around individual operators when client instrumentation already covers the exchange.

## 8. Tags of http.client.requests

Common low-cardinality tags used in HTTP client metrics:

| Tag | Meaning | Example |
| --- | --- | --- |
| method | HTTP method. | GET, POST |
| uri | URI template/route pattern if determinable. | /items/{itemId} |
| client.name | Normalized target host/service. | inventory-service |
| status | HTTP response status. | 200, 404, 503 |
| outcome | Result category. | SUCCESS, CLIENT_ERROR, SERVER_ERROR |
| exception | Exception type if the exchange ends with an exception. | ResourceAccessException |

Specific tags depend on the convention, client, and version. Inspect the meter in Actuator rather than copying the exact list from another version.

### URI templates matter for client metrics

Do not create metric tags from full URLs or raw paths containing identifiers:

~~~text
/items/1001
/items/1002
/items/1003
~~~

Use a stable template:

~~~text
/items/{itemId}
~~~

When calling a URI using a template API like `uri("/items/{itemId}", itemId)`, the framework usually has the opportunity to preserve the template. If you manually concatenate strings like `"/items/" + itemId`, instrumentation may only see the raw path and create high cardinality.

For query parameters, do not put sensitive or continuously changing values into tags. Access tokens, emails, and search terms should never become metric dimensions.

### client.name and destination

The target host also needs to be controlled. If the client calls URLs constructed from external input, the `client.name` tag can turn into thousands of different hostnames. Normalize the destination into a controlled service name or host group, avoiding recording raw user-provided hosts.

## 9. Low-cardinality and High-cardinality Values

Micrometer Observation distinguishes between low-cardinality and high-cardinality key-values. Low-cardinality values can become metric tags; high-cardinality values are better suited for tracing/logs when needed and permitted.

| Value | Low-cardinality metric tag? | Notes |
| --- | --- | --- |
| method=GET | Yes | Small set of values. |
| status=503 | Yes | Finite status codes. |
| client.name=inventory-service | Yes if destination is stable | Service name has a controlled set of values. |
| uri=/items/{itemId} | Yes | Stable template. |
| itemId=1001 | No | Value changes per request. |
| full URL with query | No | May contain PII/secrets and high cardinality. |
| request ID | No | Use log/trace correlation per policy. |

Do not put high-cardinality values into metric tags for debugging. Doing so can create too many time series and increase memory/index costs. If you need to investigate a specific request, use a trace ID or request ID managed in logs/traces.

## 10. Status, Outcome, Exception, and Timeout

An HTTP client exchange can end in several ways:
- 2xx response: usually a success.
- 4xx response: client-side error or business rejection depending on semantics.
- 5xx response: downstream server error.
- Connect timeout: failed to establish a connection within the time limit.
- Read/response timeout: timed out waiting for a response.
- DNS/TLS/connect failure: error before receiving an HTTP response.
- Cancellation: request canceled by the caller or reactive subscription.

A 4xx/5xx response does not necessarily throw an exception with every API. `WebClient retrieve()` may convert status errors into exceptions; other exchange APIs may return the response for the caller to handle. The metrics convention may record `status` if a response is present, or `exception` when the request ends with a transport error.

Do not lump every 4xx into infrastructure errors. Define outcomes according to application semantics and SLOs. A 404 when looking up a non-existent resource may be a normal business result; a 503 from a dependency may be an error requiring an alert.

Observation records duration but does not decide timeouts on its own. Configure connect/read/response timeouts on the request factory, HTTP connector, or client implementation. Timeouts that are too long can hold threads/connections; timeouts that are too short can cause false failures.

## 11. Tracing and Propagation from Client to Server

When Micrometer Tracing/OpenTelemetry or Brave is configured, HTTP client instrumentation can create a client span and inject trace context into the outbound request. The receiving service extracts the context and creates a server span as a child of the client span.

~~~mermaid
sequenceDiagram
    participant A as order-api
    participant C as Instrumented HTTP client
    participant B as inventory-api
    participant T as Trace backend

    A->>C: Call GET /items/{itemId}
    Note over C: Client span starts
    C->>B: HTTP + traceparent/baggage
    Note over B: Extract context, create server span
    B-->>C: HTTP response
    Note over C: Client span ends
    C->>T: Export client span
    B->>T: Export server span
~~~

If the trace ID changes between two services, check client instrumentation, W3C/B3 propagation, whether proxies/gateways strip or overwrite headers, whether context is lost across async/reactive boundaries, and whether the client uses the proper builder/registry. Do not send tokens, emails, or personal data in baggage.

## 12. Customizing the Observation Convention

You can customize the HTTP client Observation convention to add tags or normalize destinations. Prioritize low-cardinality fields with a finite number of values. Use a convention/handler appropriate for the Spring Framework version; do not apply a server convention to a client.

Example idea for normalizing destination:

~~~java
String serviceGroup = switch (host) {
    case "inventory.internal" -> "inventory-service";
    case "pricing.internal" -> "pricing-service";
    default -> "external";
};
~~~

Do not use raw user-provided hosts as metric tags. With a custom convention, retain default tags like `method`, `uri`, `status`/`outcome` if dashboards rely on them. Test successful requests, HTTP errors, and transport exceptions.

## 13. Inspecting via Actuator

If Actuator and the metrics endpoint are exposed in a controlled environment, query:

~~~http
GET /actuator/metrics/http.client.requests
~~~

Illustrative payload example:

~~~json
{
  "name": "http.client.requests",
  "measurements": [
    { "statistic": "COUNT", "value": 12.0 },
    { "statistic": "TOTAL_TIME", "value": 1.48 }
  ],
  "availableTags": [
    { "tag": "method", "values": ["GET", "POST"] },
    { "tag": "uri", "values": ["/items/{itemId}"] },
    { "tag": "client.name", "values": ["inventory-service"] },
    { "tag": "status", "values": ["200", "503"] }
  ]
}
~~~

The actual payload varies by client/version. You can filter the meter by an available tag:

~~~http
GET /actuator/metrics/http.client.requests?tag=client.name:inventory-service
~~~

Do not expose metrics endpoints publicly just for debugging. Protect Actuator with authentication/network policies and only expose necessary endpoints.

Prometheus series names may be `http_client_requests_seconds_count`, `_sum`, `_bucket` depending on the registry/version. Example rate query by client:

~~~promql
sum by (client_name, uri, method) (
  rate(http_client_requests_seconds_count[5m])
)
~~~

Metric/label names may be normalized by the exporter. Inspect the actual labels before creating dashboards.

## 14. Testing HTTP Client Observation

An integration test should use a fake HTTP server or mock server to control responses, delays, and exceptions.

~~~java
@SpringBootTest
class InventoryClientObservationTest {

    @Autowired
    InventoryClient inventoryClient;

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void recordsHttpClientRequest() {
        inventoryClient.findItem("1001");

        Timer timer = meterRegistry.find("http.client.requests")
                .tag("method", "GET")
                .tag("uri", "/items/{itemId}")
                .timer();

        assertThat(timer).isNotNull();
        assertThat(timer.count()).isEqualTo(1);
    }
}
~~~

The test snippet needs to configure a mock server bound to the injected `RestTemplate`; this is an illustrative skeleton and will not run out-of-the-box with every client setup. For `RestClient`/`WebClient`, use `MockRestServiceServer`/`WebTestClient` or an appropriate mock HTTP server.

Test cases that should be included:
- 200 response: timer count and status/outcome are correct.
- 404/503 response: status/outcome reflects the response according to the convention.
- Connect/read timeout: Observation stops and the `exception` tag is appropriate.
- DNS/TLS failure: does not create a hanging timer; exception is recorded.
- URI template with different IDs: `uri` tag still preserves the template.
- Retry: verify whether each attempt creates an observation/span or has an outer parent operation.
- Async/reactive: context and span are preserved properly.
- Without tracing: metrics still work if the metrics handler is configured.
- Without a metrics registry: tracing can still work if the tracing handler/exporter is configured.

## 15. Retries, Redirects, and Fan-out

A single business operation can produce multiple HTTP exchanges due to retries or parallel calls to multiple dependencies:
- One business Observation can wrap multiple client observations.
- Each retry attempt can create a separate client span/metric record depending on where instrumentation sits.
- Redirects may be handled inside the HTTP client or create another exchange depending on the implementation.
- Fan-out to multiple services creates multiple client observations, not a single timer.

Do not confuse the count of `http.client.requests` with the count of business requests. When investigating a retry storm, compare client exchange counts with inbound server request counts and monitor retry metrics separately.

## 16. Security and Privacy for HTTP Client Telemetry

Outbound URLs/headers may contain sensitive information. Do not put into metric tags or trace attributes:
- Authorization, cookies, API keys.
- Query parameters containing tokens, emails, or personal data.
- Raw path variables such as user ID/account ID if policy forbids it.
- Request/response bodies.
- Exception messages containing credentials or payloads.

Use URI templates and normalized destination groups. Logs can contain correlation IDs or safe error categories but must comply with masking policies. Do not log full outbound request headers for debugging.

## 17. Troubleshooting

| Symptom | Possible Cause | Inspection Direction |
| --- | --- | --- |
| No `http.client.requests` | Client is not instrumented, missing `ObservationRegistry`, or missing metrics handler/registry. | Check builder/bean, dependencies, and `ObservationRegistry`. |
| `RestTemplate` has meters, `RestClient` does not | Using a standalone builder or version does not auto-configure `RestClient`. | Use Boot-injected builder and check version. |
| `WebClient` has no client span | Observation/tracing registry not attached or reactive context propagation lost. | Check `WebClient.Builder` and tracing integration. |
| `uri` tag contains actual IDs | URI was concatenated instead of using a template or convention does not recognize pattern. | Use URI template API and check tag values. |
| `client.name` changes continuously | Dynamic or user-controlled host. | Normalize destination into a finite service group. |
| 503 does not show as error | Convention/outcome semantics or client API treats response as a normal value. | Check status/outcome and SLO policy. |
| Timeout has no status | No HTTP response received; exchange ended with an exception. | Check `exception` tag and timeout configuration. |
| Client/server trace IDs differ | Propagation disabled, headers stripped, or context lost. | Check W3C/B3, interceptors, and proxies. |
| Metric count greater than inbound request count | Retries, fan-out, or multiple dependency calls per request. | Analyze spans/exchanges per business request. |
| Duplicate client spans | Manual instrumentation overlapping with auto-instrumentation/agent. | Check instrumentation layers and exporter. |

## 18. Runbook: HTTP Client Call Not Observed

1. Identify the client implementation: `RestTemplate`, `RestClient`, `WebClient`, or another library.
2. Check how the client is created: injected builder from Spring or self-created builder/client.
3. Check `ObservationRegistry`: confirm the registry is attached to the client.
4. Check handlers: whether the metrics registry and tracing handler work independently.
5. Make a test request: call a local/mock endpoint returning 200 and 503.
6. Check Actuator: look for `http.client.requests` and tags `method`/`uri`/`client.name`/`status`.
7. Check traces: inspect the client span, trace ID, parent span, and propagation headers.
8. Check cardinality: send multiple path IDs and confirm the `uri` tag remains a template.
9. Check errors: test timeout/connect failure and verify the observation finishes.
10. Check duplicates: compare auto-instrumentation, OTel agent, and custom interceptors.
11. Check privacy: ensure URLs/headers/bodies do not put secrets/PII into telemetry.
12. Record versions: Spring Boot, Spring Framework, Micrometer, and the HTTP client library.

## 19. Self-Check Exercises

### Exercise 1 — Observation name

A service uses `WebClient` to call an inventory service. What is the default HTTP client meter to look for?

**Answer:** `http.client.requests`. This is the standard Observation/Meter name for HTTP client exchanges instrumented by Spring Framework/Micrometer.

### Exercise 2 — URI template

Two requests call `/items/1001` and `/items/1002` using the same endpoint. What value should the `uri` metric tag have?

**Answer:** `/items/{itemId}` if the client instrumentation receives the template. Using raw paths can create per-ID cardinality.

### Exercise 3 — No metrics but traces exist

The trace backend has client spans, but Actuator does not have `http.client.requests`. Can we conclude that client instrumentation is not working?

**Answer:** No. Tracing and metrics are separate handlers/pipelines. Check `MeterRegistry`, the metrics observation handler, and meter filters; client spans may still be created.

### Exercise 4 — 503 response

Downstream returns 503, but the client API returns the response for the caller to handle without throwing an exception. What can the Observation record?

**Answer:** It can record status 503 and the corresponding outcome if instrumentation receives the response. An exception is not required to have an error status; check the convention/version.

### Exercise 5 — Retry storm

One inbound request generates 4 outbound attempts to the same dependency. Why can the client metric count increase by 4?

**Answer:** Each HTTP exchange/attempt can be instrumented separately. The business request count remains one; inspect the retry policy and analyze attempts per operation.

### Exercise 6 — Client span does not link to server span

The client span has a different trace ID from the server span. What needs to be checked?

**Answer:** Client instrumentation, W3C/B3 propagation, outbound headers, proxy/gateway behavior, and async context propagation; not just increasing the sampling ratio.

## 20. Implementation Checklist

- [ ] HTTP client is created using a builder/client with Observation support.
- [ ] `ObservationRegistry` is attached and required handlers are active.
- [ ] Meter `http.client.requests` appears in the registry when outbound requests occur.
- [ ] Tags `method`, `uri`, `client.name`, `status`/`outcome` are verified against the version.
- [ ] URI templates are used instead of raw paths with identifiers.
- [ ] Host/destination is normalized; caller-controlled URLs are not used as metric tags.
- [ ] Connect/read/response timeouts are configured on the HTTP client.
- [ ] HTTP response errors and transport exceptions are distinguished.
- [ ] Retries/fan-out are accounted for when analyzing request counts.
- [ ] Client spans link to server spans via trace context propagation.
- [ ] Async/reactive context is tested.
- [ ] No secrets, credentials, query PII, or raw payloads in tags/logs/spans.
- [ ] Actuator metrics endpoint is protected.
- [ ] Integration tests verify success, HTTP error, timeout, URI template, and context.
- [ ] No duplicate instrumentation from custom code, starters, and agents.
- [ ] Dashboards monitor latency, error outcomes, and volume per dependency.

**Remember:** `http.client.requests` tells you how long outbound HTTP exchanges are taking and how they conclude. Use builders with Observation support, verify tags and URI templates, configure reasonable timeouts/retries, and verify that client spans link the trace context properly. Metrics show overall trends; logs and traces provide the details to find why a dependency is slow or failing while still controlling cardinality and sensitive data.
