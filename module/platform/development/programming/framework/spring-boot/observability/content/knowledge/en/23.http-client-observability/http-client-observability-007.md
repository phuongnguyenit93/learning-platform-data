# URI template in HTTP client observability with Spring Boot

When one service calls another over HTTP, each request may contain a different path, such as `/customers/101/orders` and `/customers/102/orders`. If instrumentation writes the raw URI into a metric tag, each customer ID can create a new time series. Dashboards become hard to aggregate, Prometheus cardinality grows, and storage costs increase with traffic. A **URI template** solves this by representing the endpoint with a stable structure, such as `/customers/{customerId}/orders`, so telemetry groups requests of the same type without depending on specific path values.

In the **SPRING_BOOT_OBSERVABILITY** module, URI templates are part of HTTP client observability alongside Micrometer Observation, metrics, logs, and distributed tracing. This lesson belongs to the **HTTP client observability** chapter and focuses on **URI templates**: how templates are created and passed to instrumentation, differences between a template and an expanded URI, `RestClient`/`RestTemplate`/`WebClient` integration, impact on metrics/traces, custom Observations, encoding, security, testing, and troubleshooting.

## Learning Objectives

After this lesson, you can:
1. Explain URI templates and why they are needed in HTTP client telemetry.
2. Distinguish a template URI, an expanded URI, and a raw URL.
3. Configure Spring HTTP clients so instrumentation receives the template rather than only the expanded URI.
4. Understand how Micrometer Observation uses URI templates in metrics and tracing.
5. Control the cardinality of client metrics and span attributes.
6. Handle query parameters, encoding, path variables, and URI builders.
7. Test template tags for `RestClient`, `RestTemplate`, and `WebClient`.
8. Investigate when the URI tag is `UNKNOWN`, a raw path, or when the template is lost.

## 1. What is a URI Template?

A URI template is a URI pattern with variables representing the parts that vary per request:

~~~text
Template: /customers/{customerId}/orders/{orderId}
Expanded: /customers/101/orders/9001
Expanded: /customers/205/orders/9002
Expanded: /customers/310/orders/9003
~~~

Three expanded URIs represent three different requests of the same operation type. When HTTP client instrumentation preserves the template, telemetry can group all three under one stable dimension.

| Concept | Example | Role |
| --- | --- | --- |
| URI template | /customers/{customerId}/orders/{orderId} | Logical endpoint pattern |
| Expanded URI | /customers/101/orders/9001 | Concrete URI after variable substitution |
| Raw URI | https://api.example.test/customers/101/orders?view=full | Actual URI including host/path/query |
| HTTP method | GET | HTTP operation type |
| Client name/peer | inventory-service | Logical target or dependency |

### 1.1. Why not use the expanded URI as a metric tag?

~~~text
GET /customers/101/orders
GET /customers/102/orders
GET /customers/103/orders
~~~

If the `uri` tag carries the full value, every customer ID becomes a new tag value. With millions of customers, the number of time series can grow very quickly. A URI template groups them into `GET /customers/{customerId}/orders`, allowing comparisons of request count, error ratio, and latency by endpoint type.

### 1.2. URI templates do not automatically mask data

If code builds URLs via string concatenation, the HTTP client may only see the expanded URI and not know which parts are variables. Instrumentation cannot always accurately infer every ID in a path. Use URI builder/template APIs or template-passing mechanisms supported by the client.

## 2. URI Templates in HTTP Client Observability

HTTP client instrumentation typically creates a client Observation/span for outbound requests and records method, URI/template, status, outcome, peer/service, and duration according to the version's conventions.

~~~mermaid
flowchart TD
    App["Application service"] --> Client["HTTP client"]
    Client --> Template["URI template"]
    Template --> Expand["Expand path variables"]
    Expand --> Request["HTTP request"]
    Client -. "Observation context" .-> Convention["HTTP client convention"]
    Convention --> Metrics["Client metrics"]
    Convention --> Span["Client span"]
    Metrics --> Registry["MeterRegistry"]
    Span --> Exporter["Tracing exporter"]
    Request --> Remote["Remote service"]
~~~

The request must retain template information until it reaches the observation convention. If only the expanded URI remains, the convention may not recover the exact template.

A template describes the operation the code intends to call. It is not a Trace ID, request ID, customer/order ID, query string, Authorization token, or per-request metric label. Templates should be stable and reflect the logical route. An API version like `/v1/orders` is normally part of the template because it distinguishes the API contract.

### 2.1. Client template and server route template

A client URI template describes the endpoint the client calls; a server route template describes the handler where the server receives the request. They are often similar but not necessarily identical: a client may call a gateway route, proxy, or different API version. Do not substitute the server route for the client-side template.

## 3. RestClient: Declaring Templates with Path Variables

Spring Framework provides `RestClient` with a URI builder API supporting template variables:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class CustomerApiClient {
    private final RestClient restClient;

    public CustomerApiClient(RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("https://customer-api.example.test")
                .build();
    }

    public String getOrders(String customerId) {
        return restClient.get()
                .uri("/customers/{customerId}/orders", customerId)
                .retrieve()
                .body(String.class);
    }
}
~~~

The code declares the `/customers/{customerId}/orders` template and passes `customerId` separately. The builder API expands the template into the request URI while retaining template information for compatible instrumentation components.

Avoid string concatenation for URLs if you need template telemetry:

~~~java
String uri = "/customers/" + customerId + "/orders";
~~~

### 3.1. Configuring RestClient.Builder

In Spring Boot, prefer the auto-configured builder injected from the context to preserve customizers, the observation registry, and shared settings. Calling a constructor directly to create a standalone `RestClient` can bypass configured customizers/observation conventions.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CustomerClientConfiguration {
    @Bean
    RestClient customerRestClient(RestClient.Builder builder) {
        return builder
                .baseUrl("https://customer-api.example.test")
                .build();
    }
}
~~~

When Spring Boot manages the builder, HTTP client observation can be integrated according to the version and configuration. Verify actual dependencies and auto-configuration; do not assume every self-created `RestClient` is instrumented.

### 3.2. URI builder with multiple variables

~~~java
restClient.get()
        .uri("/tenants/{tenantId}/customers/{customerId}",
                tenantId, customerId)
        .retrieve()
        .body(Customer.class);
~~~

The template has two variables but produces only one operation type. Avoid putting `tenantId`/`customerId` into Observation names or metric tags.

## 4. RestTemplate: Passing the URI Template into Exchange

`RestTemplate` has overloads supporting URI templates and variables:

~~~java
import org.springframework.web.client.RestTemplate;

public Customer getCustomer(
        RestTemplate restTemplate,
        String customerId
) {
    return restTemplate.getForObject(
            "https://customer-api.example.test/customers/{customerId}",
            Customer.class,
            customerId
    );
}
~~~

This invocation preserves the URI pattern in the client API. If you build a `URI` from a concatenated string, template metadata can be lost.

### 4.1. RestTemplate needs instrumentation configuration

Use a `RestTemplate` created from Spring Boot's builder/configuration to receive the corresponding customizers and observation integration:

~~~java
@Bean
RestTemplate customerRestTemplate(RestTemplateBuilder builder) {
    return builder.build();
}
~~~

Builder names/imports and auto-configuration depend on the Spring Boot version. Check the existing builder bean and Micrometer Observation/Tracing configuration before adding manual interceptors.

### 4.2. Avoiding duplicate client spans

If HTTP client instrumentation already creates an Observation/span, a custom interceptor that creates an extra client span for the same request can put two equivalent spans in the trace and double-count metrics. Custom interceptors should only add metadata or behavior that is genuinely missing, while preserving the lifecycle and parent context.

## 5. WebClient: URI Templates in the Reactive HTTP Client

`WebClient` supports URI builder/template variables:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class InventoryWebClient {
    private final WebClient webClient;

    public InventoryWebClient(WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("https://inventory-api.example.test")
                .build();
    }

    public Mono<Inventory> getInventory(String sku) {
        return webClient.get()
                .uri("/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(Inventory.class);
    }
}
~~~

When using the Spring Boot-managed builder, customizers and observation integration can be applied. `WebClient` is reactive; context propagation differs from pure `ThreadLocal`. Do not assume MDC or thread-local context is always present when the pipeline switches schedulers.

### 5.1. URI builder function

You can use `UriBuilder` to construct encoded query parameters:

~~~java
webClient.get()
        .uri(builder -> builder
                .path("/inventory/{sku}")
                .queryParam("include", "{include}")
                .build(sku, "availability"))
        .retrieve()
        .bodyToMono(Inventory.class);
~~~

Check the overloads and variable encoding behavior of your Spring Framework version. Do not manually concatenate query strings because it can cause incorrect encoding and accidentally expose dynamic values in telemetry.

### 5.2. WebClient observation context

`WebClient` instrumentation can record the URI template if the request is built with the template API and the observation convention receives that information. If only a complete `URI` is passed, the template may not exist. Verify actual observation/span tags in tests.

## 6. How URI Templates Affect Metrics and Traces

URI templates are typically useful as low-cardinality dimensions for HTTP client metrics. For traces, the URI template is also an attribute describing the operation, whereas the expanded URL may be unnecessary or need filtering.

| Dimension | Example | Notes |
| --- | --- | --- |
| method | GET | Small set |
| uri | /customers/{customerId}/orders | Use template |
| status | 200, 404, 503 | Finite values |
| outcome | SUCCESS, CLIENT_ERROR, SERVER_ERROR | Stable classification |
| client/service | customer-api | Logical dependency name |
| exception | IOException | Avoid dynamic exception messages |

Meter names and tag keys depend on the Spring Boot/Micrometer version and registry. Inspect the actual meter instead of hard-coding assumptions.

### 6.1. PromQL examples

~~~promql
sum by (method, uri) (
  rate(http_client_requests_seconds_count[5m])
)
~~~

5xx error ratio from the client perspective:

~~~promql
sum(rate(http_client_requests_seconds_count{status=~"5.."}[5m]))
/
sum(rate(http_client_requests_seconds_count[5m]))
~~~

p95 latency with classic histograms:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_client_requests_seconds_bucket[5m])
  )
)
~~~

These queries assume the registry exports the `http_client_requests` meter in seconds with `method`/`uri`/`status` labels. Actual names, units, buckets, and labels may differ by version/configuration. Inspect scrape output before using dashboards.

### 6.2. Metric tags and span attributes have different budgets

Low-cardinality URI templates fit metrics. Spans can hold more detailed metadata, yet raw URIs/query strings can still increase indexing/storage costs or expose data. Do not copy every path/query value into span attributes.

## 7. Query Parameters, Encoding, and Path Variables

URI templates usually describe the path; query parameters can vary per request and sometimes contain sensitive data.

~~~text
Template:
  /search?category={category}&page={page}
Request A:
  /search?category=books&page=1
Request B:
  /search?category=books&page=2
~~~

If query values are placed into metric tags, cardinality grows with filter/page values. Typically, only the path template is used for metric dimensions, not the full query string.

### 7.1. Encoding path variables

Path values may contain spaces, slashes, Unicode, or reserved characters. Use Spring's URI builder to encode variables according to URI rules. Avoid double-encoding or string concatenation. Test special characters to confirm the request URI is valid and telemetry still uses the template.

### 7.2. Query strings can contain secrets

Some poorly designed APIs place API keys, tokens, or PII in the query string. Full URIs can appear in logs, spans, proxy access logs, or exception messages. Do not log/export raw query strings; move credentials to secure headers and redact URIs if the system might record sensitive values.

### 7.3. Base URL and host

Hosts can vary across environments or load balancing. Putting raw host/port into metric tags is not always necessary. If you need to distinguish dependencies, use a stable logical name such as `customer-api` or `inventory-service`. If host is important for investigation, it can be stored in controlled trace attributes while weighing cardinality and privacy.

## 8. Custom ObservationConvention for HTTP Clients

When you need to standardize client metadata, use an `ObservationConvention` or custom Observation matching the client's extension point. Do not create a second Observation for the same HTTP request if the client already instruments itself.

A custom business Observation wrapping the client call can add the business operation:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class PricingService {
    private final RestClient restClient;
    private final ObservationRegistry registry;

    public PricingService(RestClient restClient, ObservationRegistry registry) {
        this.restClient = restClient;
        this.registry = registry;
    }

    public Price getPrice(String productCode) {
        return Observation.createNotStarted("pricing.lookup", registry)
                .lowCardinalityKeyValue("pricing.source", "catalog")
                .observe(() -> restClient.get()
                        .uri("/products/{code}/price", productCode)
                        .retrieve()
                        .body(Price.class));
    }
}
~~~

`pricing.lookup` is a business operation wrapping the HTTP client call; HTTP client instrumentation still observes the HTTP request. The `pricing.source` tag has a small value set. Do not add `productCode` to a low-cardinality tag.

### 8.1. Do not use dynamic URIs as observation names

Do not set an observation name like `GET /customers/101/orders`. Dynamic names make metric dimensions unstable and can leak data. Use a stable operation name and separate URI template.

## 9. URI Templates, Tracing Propagation, and Correlation

The URI template describes the target being called; trace context describes the relationship between operations. The two concepts complement each other.

~~~mermaid
sequenceDiagram
    participant Order as order-service
    participant Client as HTTP client
    participant Inventory as inventory-service
    participant Collector
    Order->>Client: GET /inventory/{sku}
    Note over Client: Client span + URI template
    Client->>Inventory: GET /inventory/ABC-1 + traceparent
    Note over Inventory: Server span + route template
    Inventory-->>Client: HTTP 200
    Client-->>Order: Inventory response
    Order->>Collector: Export client span
    Inventory->>Collector: Export server span
~~~

The URI template tells which endpoint the operation calls; the Trace ID links the client span with the server span; the Span ID identifies the operation; resource attributes identify the emitting service; logs can carry `traceId`/`spanId` via MDC.

If the URI template is lost, traces can still exist, but endpoint grouping in metrics/traces becomes less useful. If trace propagation is lost, the URI template can still record the client operation, but it cannot link to the downstream server span.

## 10. Controlling Cardinality and Sensitive Data

| Value | Metric tag? | Trace attribute? | Notes |
| --- | --- | --- | --- |
| URI template | Yes | Yes, per convention | Stable |
| Expanded path with ID | No | Avoid or redact | High cardinality |
| Full query string | No | Not by default | May contain PII/secrets |
| HTTP method | Yes | Yes | Small set |
| Status/outcome | Yes | Yes | Finite set |
| Dependency logical name | Yes | Yes | Normalized |
| Trace ID | No | Context field | Correlation, not a label |
| Customer ID | No | Only when needed and approved | PII/cardinality |
| Authorization token | No | No | Secret |
| Exception message | No | Not by default | May contain dynamic values |

### 10.1. Estimating cardinality

If a client metric has 20 URI templates, 5 HTTP methods, 6 status groups, and 4 dependency names, the simple maximum number of combinations is:

\[
20 \times 5 \times 6 \times 4 = 2,400
\]

If 20 templates are replaced with 100,000 expanded paths, potential combinations scale with the number of actual paths. This is an illustrative model; actual series depend on observed combinations and other labels.

### 10.2. Attribute filtering and redaction

Establish an allowlist of required attributes. If a URI has tokens or PII in the query, redaction should happen before export/logging. Do not rely on the backend hiding fields in the UI because the payload has already left the process.

## 11. Testing URI Templates

Verify not only that requests are sent to the right endpoint, but also that observations/metrics/tracing record the right template.

### 11.1. Testing URI expansion

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.web.util.UriComponentsBuilder;
import static org.assertj.core.api.Assertions.assertThat;

class CustomerUriTest {
    @Test
    void expandsCustomerTemplate() {
        String uri = UriComponentsBuilder
                .fromPath("/customers/{customerId}/orders")
                .buildAndExpand("101")
                .encode()
                .toUriString();

        assertThat(uri).isEqualTo("/customers/101/orders");
    }
}
~~~

This test only verifies URI expansion; it does not prove that HTTP client observation preserves the template.

### 11.2. Testing Observation with the client

Use a test server (e.g., MockWebServer/WireMock or an embedded HTTP server) and an HTTP client configured like production:

1. Create a request using the `/customers/{customerId}/orders` template.
2. Send several different customer IDs.
3. Capture Observation or meter events.
4. Assert the URI tag remains the template.
5. Assert the actual request was sent to the right expanded path.
6. Assert no customer ID appears in metric tags.
7. Return 4xx/5xx responses and check status/outcome.
8. If tracing is enabled, verify the client span has the template attribute and trace context is injected.

### 11.3. Test each client implementation separately

`RestClient`, `RestTemplate`, and `WebClient` have distinct builder APIs, instrumentation, and lifecycles. Do not assume `WebClient` preserves templates just because `RestClient` was tested. Write tests for each actual client implementation.

### 11.4. Testing queries and encoding

Use query values with spaces, Unicode, reserved characters, and mock token-like values. Verify the request URI is encoded properly; the template contains no expanded IDs; sensitive queries are not exported/logged; and metrics cardinality does not grow with query values.

## 12. Troubleshooting URI Templates

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Metric `uri` is `UNKNOWN` | Client only received expanded URI or template was not passed | Use URI template overload/builder and check observation context |
| Metric `uri` contains customer ID | URL created via string concatenation | Use template API with variables |
| `RestClient` has template but `WebClient` does not | Client API/instrumentation differs | Test each client builder separately |
| Template encoded as `%7B...%7D` | Variables/template encoded in wrong order | Use appropriate URI builder API |
| Query values create many series | Query string used as tag | Remove query from metric dimensions |
| Metrics double-counted | Auto-instrumentation and custom interceptor both recording | Remove duplicate instrumentation |
| Span lacks URI template | Convention did not receive template or client did not provide it | Inspect span attributes |
| Raw token appears in trace | Query/header captured | Redact/allowlist before export |
| Changing host increases series | Raw host/port used as tag | Use logical dependency name |
| URI broken with slash/Unicode | Manual concatenation or manual encoding | Use `UriBuilder` and test encoding |
| Client trace does not link to server | Propagation headers/context wrong | Check W3C `traceparent` |
| HTTP client has no observation | Self-created builder bypassed Boot customizer | Use auto-configured builder and check registry |

### 12.1. Investigation workflow

1. Identify the actual client implementation: `RestClient`, `RestTemplate`, or `WebClient`.
2. Check which builder created the client and whether auto-configuration/customizers are applied.
3. Inspect whether the request URI is constructed using a template overload or a plain expanded URI.
4. Capture actual Observation/meter/span data to inspect URI tags/attributes.
5. Compare the template with the sent request URL.
6. Check queries, encoding, hosts, and sensitive data.
7. Check whether instrumentation is registered twice.
8. If traces do not link downstream, check propagation independently of the URI template.

## 13. Production Checklist

| Criterion | Evidence |
| --- | --- |
| Stable URI templates | Path variables use placeholders |
| No expanded URI as metric tag | Test multiple IDs for the same template |
| Managed client builders | Spring Boot customizers/observation applied |
| `RestClient`/`RestTemplate`/`WebClient` tested | Each implementation preserves templates |
| HTTP method/status/outcome standardized | Stable dashboards |
| Query strings controlled | No token/PII exported |
| Path encoding accurate | Test slashes, Unicode, and reserved chars |
| Stable dependency names | No dynamic hosts as metric labels |
| No duplicate instrumentation | One HTTP request has one primary client observation |
| Tracing propagation works | Client/server spans share trace |
| Cardinality measured | Series count per template stays within budget |
| Redaction before export | Not relying on UI masking |
| Runbook available | Handles `UNKNOWN`/raw URI/missing spans |

## 14. Hands-on Exercise: Standardizing URI Templates for HTTP Clients

**Context:** `order-service` calls `customer-api`, `inventory-api`, and `pricing-api`. Metrics currently record expanded URIs containing `customerId`/`productCode`, causing cardinality growth. Some `WebClient` spans lack a URI template.

**Tasks:**
1. Inventory the HTTP clients in use: `RestClient`, `RestTemplate`, and `WebClient`.
2. Replace concatenated URL strings with URI templates and path variables.
3. Use Spring Boot-managed builders to retain observation customizers.
4. Send multiple customer IDs to the same endpoint and verify the metric URI remains `/customers/{customerId}/orders`.
5. Add query parameters via `UriBuilder` and test encoding.
6. Collect Observation/meter/span data to compare templates with expanded URIs.
7. Verify status/outcome and latency when remote returns 4xx/5xx.
8. Verify the client span propagates `traceparent` to the server and both spans share the trace ID.
9. Redact sensitive queries/headers; verify no tokens or PII appear in logs/traces.
10. Write cardinality regression tests and a runbook for when the URI tag becomes `UNKNOWN` or a raw path.

**Expected outcome:** client code uses URI templates, metrics group endpoints accurately, traces contain safe operation metadata, dedicated tests exist for each client implementation, and a guide exists for investigating lost URI templates.

## 15. Remember

A **URI template** is a stable endpoint pattern, e.g., `/customers/{customerId}/orders`; an expanded URI is a concrete request, e.g., `/customers/101/orders`. Use the template APIs of `RestClient`, `RestTemplate`, or `WebClient` so HTTP client instrumentation can preserve this metadata. Avoid string-concatenating URLs when template-aware telemetry is needed.

URI templates keep metric cardinality low and make trace operation descriptions easy to understand. Do not put raw query strings, customer IDs, tokens, or dynamic URLs into metric tags. Use Spring Boot-managed builders, test each client implementation, verify actual URI tags/span attributes, and keep trace context propagation independent of templates. Metrics serve request/error/latency aggregation; traces help investigate dependency calls; logs provide correlated and redacted events.

**References:**
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Spring Framework — RestClient](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html#rest-restclient)
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Spring Boot — HTTP Client Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer Observation — Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [OpenTelemetry — HTTP Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/http/)
